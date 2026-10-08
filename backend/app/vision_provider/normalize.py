"""Turn raw (untrusted) proposals into ``Observation`` objects.

Deterministic steps happen here: pixel conversion, nearest-hole snapping via
the calibrated homography, catalog identification, template mapping, colour
cues. Every observation starts as ``proposed``.
"""

from __future__ import annotations

import uuid

import cv2
import numpy as np

from ..catalog import decode_color_bands, format_ohms, normalize_board_pin
from ..image_processing import nearest_hole
from ..schemas import (
    Candidate,
    Endpoint,
    Evidence,
    Observation,
    Point,
)
from .base import ProposeContext, RawEndpoint, RawItem, RawProposals

CONF_ORDER = ["uncertain", "low", "medium", "high"]
SNAP_STRONG = 0.35  # pitch units: confident snap
SNAP_MAX = 0.8  # pitch units: beyond this the endpoint is not on a hole

# Models describe parts in free text; only this closed mapping reaches the catalog.
KIND_TO_CATALOG_KIND = {
    "resistor": "resistor",
    "led": "led",
    "light emitting diode": "led",
    "wire": "wire",
    "jumper": "wire",
    "jumper wire": "wire",
}
BOARD_KINDS = {"arduino", "dev_board", "board", "microcontroller", "arduino uno"}


def _cap(conf: str, ceiling: str) -> str:
    return CONF_ORDER[min(CONF_ORDER.index(conf), CONF_ORDER.index(ceiling))]


def _to_px(norm_yx: list[float], w: int, h: int) -> tuple[float, float]:
    return norm_yx[1] / 1000.0 * w, norm_yx[0] / 1000.0 * h


def _polygon(box: list[float] | None, w: int, h: int) -> list[Point]:
    if not box:
        return []
    y0, x0, y1, x1 = box
    px0, py0 = _to_px([y0, x0], w, h)
    px1, py1 = _to_px([y1, x1], w, h)
    return [Point(x=px0, y=py0), Point(x=px1, y=py0), Point(x=px1, y=py1), Point(x=px0, y=py1)]


def line_color_name(image_bgr: np.ndarray, p0: Point, p1: Point) -> str | None:
    """Colour name sampled along the segment between two wire endpoints (OpenCV cue).

    Sampling the line, not the bounding box, keeps the table and breadboard out of the estimate.
    """
    h, w = image_bgr.shape[:2]
    n = int(max(abs(p1.x - p0.x), abs(p1.y - p0.y)))
    if n < 6:
        return None
    xs = np.linspace(p0.x, p1.x, n)[2:-2]
    ys = np.linspace(p0.y, p1.y, n)[2:-2]
    ok = (xs >= 1) & (xs < w - 1) & (ys >= 1) & (ys < h - 1)
    if ok.sum() < 4:
        return None
    px = image_bgr[ys[ok].astype(int), xs[ok].astype(int)].reshape(-1, 1, 3)
    hsv = cv2.cvtColor(px, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    if np.mean(hsv[:, 2] < 70) > 0.6:
        return "black"
    colored = hsv[(hsv[:, 1] > 80) & (hsv[:, 2] > 70)]
    if len(colored) < 0.5 * len(hsv):
        return "white" if np.mean((hsv[:, 1] < 40) & (hsv[:, 2] > 170)) > 0.6 else None
    hue = float(np.median(colored[:, 0])) * 2  # degrees
    for lo, hi, name in [(0, 15, "red"), (15, 45, "orange"), (45, 70, "yellow"), (70, 170, "green"), (170, 260, "blue"), (260, 330, "purple"), (330, 361, "red")]:
        if lo <= hue < hi:
            return name
    return None


def _resolve_endpoint(
    raw: RawEndpoint, ctx: ProposeContext, H: np.ndarray | None, conf: str, notes: list[Evidence]
) -> tuple[Endpoint, str]:
    """Return (endpoint, confidence). Snapping is done by OpenCV geometry, not by the model."""
    w, h = ctx.width, ctx.height
    board_part = ctx.catalog.parts[ctx.template.supported_board_id]
    pin = normalize_board_pin(raw.board_pin, board_part) if raw.board_pin else None

    if raw.point is not None and H is not None:
        px, py = _to_px(raw.point, w, h)
        hole, dist = nearest_hole(H, px, py, ctx.catalog.breadboards[ctx.template.breadboard_model_id])
        pt = Point(x=px, y=py)
        if dist <= SNAP_MAX:
            if dist > SNAP_STRONG:
                conf = _cap(conf, "medium")
            note = f"Endpoint snapped to hole {hole} (offset {dist:.2f} pitch)."
            if raw.hole and raw.hole.lower().replace("-", "") != hole:
                conf = _cap(conf, "uncertain")
                note += f" The model said {raw.hole}; the calibrated geometry disagrees, so this needs your review."
            notes.append(Evidence(source="opencv", note=note))
            return Endpoint(kind="breadboard_hole", hole=hole, point=pt), conf
        if pin:
            notes.append(Evidence(source="gemma", note=f"Endpoint is outside the breadboard grid; the model read the Arduino pin label as '{raw.board_pin}'."))
            return Endpoint(kind="board_pin", board_pin=pin, point=pt), _cap(conf, "medium")
        if raw.board_pin:
            notes.append(Evidence(source="gemma", note=f"The model read pin label '{raw.board_pin}', which is not in the verified catalog."))
            return Endpoint(kind="board_pin", board_pin=raw.board_pin, point=pt), _cap(conf, "low")
        return Endpoint(kind="off_grid", point=pt, note="Outside the calibrated grid and no pin label read."), _cap(conf, "low")

    if raw.hole:
        notes.append(Evidence(source="gemma", note=f"Hole '{raw.hole}' was stated by the model without a pixel position, so it could not be verified against the grid."))
        return Endpoint(kind="breadboard_hole", hole=raw.hole.lower().replace("-", "")), _cap(conf, "medium")
    if raw.board_pin:
        return Endpoint(kind="board_pin", board_pin=pin or raw.board_pin), _cap(conf, "medium" if pin else "low")
    return Endpoint(kind="unknown", note="Endpoint not located."), "uncertain"


def normalize(
    raw: RawProposals, ctx: ProposeContext, image_bgr: np.ndarray, source: str
) -> list[Observation]:
    """``source`` is ``gemma`` or ``demo``."""
    H = np.array(ctx.calibration.homography) if ctx.calibration.homography else None
    tpl, cat = ctx.template, ctx.catalog
    by_kind = {p.kind: p for p in cat.parts.values()}
    refs_by_part: dict[str, list[str]] = {}
    for inst in tpl.instances:
        refs_by_part.setdefault(inst.part_id, []).append(inst.ref)

    out: list[Observation] = []
    origin_note = (
        "Proposed by Gemma 4 from the photo."
        if source == "gemma"
        else "DEMO provider: scripted fixture output in Gemma's response format. No model was called."
    )

    def new_id() -> str:
        return "ob_" + uuid.uuid4().hex[:8]

    for item in raw.items:
        poly = _polygon(item.box_2d, ctx.width, ctx.height)
        evidence = [Evidence(source=source, note=origin_note)]  # type: ignore[arg-type]
        conf = {"high": "high", "medium": "medium", "low": "low"}[item.confidence]

        if item.kind in BOARD_KINDS:
            out.append(
                Observation(
                    id=new_id(), image_session_id=ctx.session_id, observation_type="board",
                    candidate_part_or_endpoint=Candidate(part_id=ctx.template.supported_board_id, label=item.label_text, description=item.description),
                    bounding_box_or_polygon=poly, confidence_label=conf, source=source,  # type: ignore[arg-type]
                    evidence=evidence, display_name="Development board (UNO R3 expected)",
                )
            )
            continue

        cat_kind = KIND_TO_CATALOG_KIND.get(item.kind)
        part = by_kind.get(cat_kind) if cat_kind else None

        if part is None:
            out.append(
                Observation(
                    id=new_id(), image_session_id=ctx.session_id, observation_type="component",
                    candidate_part_or_endpoint=Candidate(part_id=None, kind_hint=item.kind, label=item.label_text, description=item.description),
                    bounding_box_or_polygon=poly, confidence_label=_cap(conf, "low"), source=source,  # type: ignore[arg-type]
                    evidence=evidence + [Evidence(source="catalog", note=f"'{item.kind}' is not in the supported catalog for this template.")],
                    display_name=f"Unrecognised object ({item.kind})",
                )
            )
            continue

        endpoints: dict[str, Endpoint] = {}
        ep_conf = conf
        term_names = part.terminal_names
        for term in term_names:
            raw_ep = item.leads.get(term)
            if raw_ep is None:
                endpoints[term] = Endpoint(kind="unknown", note="Not located by the model.")
                ep_conf = "uncertain"
                continue
            ep, c = _resolve_endpoint(raw_ep, ctx, H, conf, evidence)
            endpoints[term] = ep
            ep_conf = CONF_ORDER[min(CONF_ORDER.index(ep_conf), CONF_ORDER.index(c))]

        cand = Candidate(
            part_id=part.id, kind_hint=item.kind, label=item.label_text,
            color_bands=item.color_bands, color=item.color, endpoints=endpoints,
            orientation_note=item.orientation_note, description=item.description,
        )
        otype = "wire" if part.kind == "wire" else "component"
        name = part.display_name

        if part.kind in ("resistor", "led"):
            refs = refs_by_part.get(part.id, [])
            cand.template_ref = refs[0] if len(refs) == 1 else None
        if part.kind == "resistor":
            decoded = decode_color_bands(item.color_bands)
            if decoded is not None:
                cand.value_ohms = decoded
                evidence.append(Evidence(source="catalog", note=f"Colour bands {'-'.join(item.color_bands or [])} decode to {format_ohms(decoded)} (IEC 60062)."))
                name = f"Resistor {cand.template_ref or ''} · {format_ohms(decoded)} (bands read by {source})".replace("  ", " ")
            else:
                name = f"Resistor {cand.template_ref or ''} · value not read".replace("  ", " ")
                ep_conf = _cap(ep_conf, "low")
        elif part.kind == "led":
            name = f"LED {cand.template_ref or ''}".strip()
            if not item.orientation_note:
                ep_conf = _cap(ep_conf, "low")
                evidence.append(Evidence(source=source, note="No polarity cue (lead length / flat edge) reported; polarity needs your confirmation."))  # type: ignore[arg-type]
            else:
                evidence.append(Evidence(source=source, note=f"Polarity cue: {item.orientation_note}"))  # type: ignore[arg-type]
        else:  # wire
            a, b = endpoints.get("end_a"), endpoints.get("end_b")
            if a and b and a.point and b.point:
                cue = line_color_name(image_bgr, a.point, b.point)
                if cue:
                    evidence.append(Evidence(source="opencv", note=f"Colour sampled along the wire: {cue}."))
                    cand.color = cue  # OpenCV measurement takes precedence over the model's colour word
            name = f"{(cand.color or '').capitalize()} jumper wire".strip()
            desc = lambda e: e.hole or e.board_pin or e.kind
            if a and b:
                name += f" {desc(a)} → {desc(b)}"

        out.append(
            Observation(
                id=new_id(), image_session_id=ctx.session_id, observation_type=otype,  # type: ignore[arg-type]
                candidate_part_or_endpoint=cand, bounding_box_or_polygon=poly,
                confidence_label=ep_conf, source=source,  # type: ignore[arg-type]
                evidence=evidence, display_name=name,
            )
        )

    for reg in raw.obscured_regions:
        out.append(
            Observation(
                id=new_id(), image_session_id=ctx.session_id, observation_type="obscured_region",
                candidate_part_or_endpoint=Candidate(description=reg.description or "Area too unclear to inspect"),
                bounding_box_or_polygon=_polygon(reg.box_2d, ctx.width, ctx.height),
                confidence_label="medium", source=source,  # type: ignore[arg-type]
                evidence=[Evidence(source=source, note=origin_note)],  # type: ignore[arg-type]
                display_name="Obscured / unclear area",
            )
        )
    return out
