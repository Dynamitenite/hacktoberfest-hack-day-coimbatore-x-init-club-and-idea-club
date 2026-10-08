#!/usr/bin/env python3
"""Generate the synthetic demo photos and their scripted provider output.

The two fixtures are *renders*, not photographs of real hardware. They differ in
exactly one place: the ground jumper lands in row 16 (seeded mismatch) or row 15
(corrected). Hole positions are computed from the same grid model the app uses,
so the scripted proposals are geometrically consistent with the picture.

Run:  python scripts/generate_fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.catalog import load_catalog  # noqa: E402

OUT = BACKEND / "data" / "fixtures"
S = 34  # flat-canvas pixels per 0.1 inch pitch
FLAT_W, FLAT_H = 1400, 1000
OX, OY = 190, 480  # flat position of hole a1
W, H = 1280, 960
SRC_QUAD = np.float32([[0, 0], [FLAT_W, 0], [FLAT_W, FLAT_H], [0, FLAT_H]])
DST_QUAD = np.float32([[70, 50], [1215, 22], [1262, 925], [28, 890]])
WARP = cv2.getPerspectiveTransform(SRC_QUAD, DST_QUAD)

cat = load_catalog()
BOARD = cat.breadboards["half_400"]


def flat_hole(hole: str) -> tuple[float, float]:
    col, row = hole[0], int(hole[1:])
    return OX + (row - 1) * S, OY + BOARD.column_offsets_pitch[col] * S


def warp_pt(x: float, y: float) -> tuple[float, float]:
    v = WARP @ np.array([x, y, 1.0])
    return float(v[0] / v[2]), float(v[1] / v[2])


def hole_px(hole: str) -> tuple[float, float]:
    return warp_pt(*flat_hole(hole))


# Arduino digital header, mirrored so the pins read left-to-right: 8 9 10 11 12 13 GND AREF
HEADER = ["8", "~9", "~10", "~11", "12", "13", "GND", "AREF"]
HEADER_Y = 330
HEADER_X0 = OX + 7.5 * S  # puts pin "~9" over row 10 and "GND" over row 15


def header_pin(label: str) -> tuple[float, float]:
    idx = HEADER.index(label)
    return HEADER_X0 + idx * S + S * 0.5, HEADER_Y + S * 0.6


def draw_scene(gnd_row: int) -> np.ndarray:
    img = np.zeros((FLAT_H, FLAT_W, 3), np.uint8)
    # table
    for y in range(FLAT_H):
        img[y, :] = (70 + y // 40, 92 + y // 45, 120 + y // 40)
    rng = np.random.default_rng(7)
    grain = rng.normal(0, 5, (FLAT_H, FLAT_W, 1)).astype(np.float32)
    img = np.clip(img.astype(np.float32) + grain, 0, 255).astype(np.uint8)

    # breadboard body + rails
    bx0, by0 = int(OX - 1.7 * S), int(OY - 3.3 * S)
    bx1, by1 = int(OX + 29 * S + 1.7 * S), int(OY + 11 * S + 3.3 * S)
    cv2.rectangle(img, (bx0 - 4, by0 - 4), (bx1 + 4, by1 + 4), (190, 190, 190), -1)
    cv2.rectangle(img, (bx0, by0), (bx1, by1), (232, 236, 238), -1)
    cy_mid = OY + 5.5 * S
    cv2.rectangle(img, (bx0, int(cy_mid - 0.35 * S)), (bx1, int(cy_mid + 0.35 * S)), (186, 190, 194), -1)  # centre channel
    for y_r, color in [(OY - 2.4 * S, (60, 60, 220)), (OY - 1.55 * S, (200, 90, 50)), (OY + 12.55 * S, (60, 60, 220)), (OY + 13.4 * S, (200, 90, 50))]:
        cv2.line(img, (bx0 + int(0.7 * S), int(y_r - 0.45 * S)), (bx1 - int(0.7 * S), int(y_r - 0.45 * S)), color, 2)
    # holes
    hs = int(0.17 * S)
    for r in range(1, 31):
        for c in BOARD.columns:
            x, y = flat_hole(f"{c}{r}")
            cv2.rectangle(img, (int(x) - hs, int(y) - hs), (int(x) + hs, int(y) + hs), (205, 208, 210), -1)
            cv2.rectangle(img, (int(x) - hs + 2, int(y) - hs + 2), (int(x) + hs - 2, int(y) + hs - 2), (40, 40, 44), -1)
    for r in range(1, 26):  # rail holes (not modelled by the app)
        for k, off in enumerate([-2.4, -1.55, 12.55, 13.4]):
            if r % 6 == 0:
                continue
            x = OX + (r - 1 + 1.2) * S
            y = OY + off * S - 0.45 * S
            cv2.rectangle(img, (int(x) - hs + 3, int(y) - hs + 3), (int(x) + hs - 3, int(y) + hs - 3), (60, 60, 64), -1)
    # silkscreen
    for r in (1, 5, 10, 15, 20, 25, 30):
        x, _ = flat_hole(f"a{r}")
        cv2.putText(img, str(r), (int(x) - 8, int(OY - 0.75 * S)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (110, 110, 110), 1, cv2.LINE_AA)
    for c in BOARD.columns:
        x, y = flat_hole(f"{c}1")
        cv2.putText(img, c, (int(OX - 1.25 * S), int(y) + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (110, 110, 110), 1, cv2.LINE_AA)

    # Arduino board (top view) and its header
    cv2.rectangle(img, (int(HEADER_X0 - 6.5 * S), 40), (int(HEADER_X0 + 18 * S), HEADER_Y + int(1.3 * S)), (120, 110, 20), -1)
    cv2.rectangle(img, (int(HEADER_X0 - 6.5 * S), 40), (int(HEADER_X0 + 18 * S), HEADER_Y + int(1.3 * S)), (90, 80, 10), 3)
    cv2.rectangle(img, (int(HEADER_X0 - 6 * S), 70), (int(HEADER_X0 - 1.8 * S), 230), (170, 170, 175), -1)  # USB-B shell
    cv2.putText(img, "ARDUINO UNO", (int(HEADER_X0 + 2 * S), 150), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (230, 230, 200), 2, cv2.LINE_AA)
    hx0, hx1 = int(HEADER_X0), int(HEADER_X0 + len(HEADER) * S)
    cv2.rectangle(img, (hx0, HEADER_Y), (hx1, HEADER_Y + int(1.2 * S)), (25, 25, 28), -1)
    for i, label in enumerate(HEADER):
        px, py = header_pin(label)
        cv2.rectangle(img, (int(px) - 5, int(py) - 5), (int(px) + 5, int(py) + 5), (150, 150, 150), -1)
        cv2.putText(img, label, (int(px) - 12, HEADER_Y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (240, 240, 240), 1, cv2.LINE_AA)

    # resistor R1: c10 .. c14, bands red red brown gold
    x1, y1 = flat_hole("c10")
    x2, y2 = flat_hole("c14")
    cv2.line(img, (int(x1), int(y1)), (int(x1 + 0.6 * S), int(y1 - 0.9 * S)), (170, 170, 175), 3)
    cv2.line(img, (int(x2), int(y2)), (int(x2 - 0.6 * S), int(y2 - 0.9 * S)), (170, 170, 175), 3)
    bx_a, bx_b = int(x1 + 0.6 * S), int(x2 - 0.6 * S)
    by_ = int(y1 - 0.9 * S)
    cv2.line(img, (bx_a, by_), (bx_b, by_), (170, 170, 175), 3)
    body0, body1 = int(x1 + 0.9 * S), int(x2 - 0.9 * S)
    cv2.rectangle(img, (body0, by_ - int(0.42 * S)), (body1, by_ + int(0.42 * S)), (150, 190, 215), -1)  # tan body (BGR)
    span = body1 - body0
    for frac, bgr in [(0.18, (30, 30, 200)), (0.36, (30, 30, 200)), (0.54, (30, 80, 140)), (0.84, (60, 160, 200))]:
        xb = body0 + int(span * frac)
        cv2.rectangle(img, (xb - 3, by_ - int(0.42 * S)), (xb + 3, by_ + int(0.42 * S)), bgr, -1)

    # LED: anode d14 (longer), cathode d15 ; dome toward the f-j side
    ax, ay = flat_hole("d14")
    kx, ky = flat_hole("d15")
    cv2.line(img, (int(ax), int(ay)), (int(ax), int(ay + 1.5 * S)), (180, 180, 185), 3)  # longer lead
    cv2.line(img, (int(kx), int(ky)), (int(kx), int(ky + 1.05 * S)), (180, 180, 185), 3)  # shorter lead
    dcx, dcy = (ax + kx) / 2, ay + 2.1 * S
    cv2.circle(img, (int(dcx), int(dcy)), int(1.05 * S), (35, 35, 205), -1)
    cv2.circle(img, (int(dcx), int(dcy)), int(1.05 * S), (20, 20, 150), 2)
    cv2.circle(img, (int(dcx - 0.3 * S), int(dcy - 0.3 * S)), int(0.28 * S), (140, 140, 255), -1)
    cv2.line(img, (int(dcx + 1.05 * S), int(dcy - 0.7 * S)), (int(dcx + 1.05 * S), int(dcy + 0.7 * S)), (20, 20, 150), 3)  # flat rim, cathode side

    # jumpers
    def jumper(p0, p1, color, via=None):
        pts = [p0] + ([via] if via else []) + [p1]
        arr = np.array(pts, np.int32).reshape(-1, 1, 2)
        cv2.polylines(img, [arr], False, tuple(int(c * 0.6) for c in color), int(0.36 * S) + 3, cv2.LINE_AA)
        cv2.polylines(img, [arr], False, color, int(0.36 * S), cv2.LINE_AA)
        for p in (p0, p1):
            cv2.circle(img, (int(p[0]), int(p[1])), int(0.2 * S), (210, 210, 215), -1)

    d9 = header_pin("~9")
    jumper(d9, flat_hole("a10"), (60, 190, 60), via=(d9[0], OY - 2.8 * S))
    gnd = header_pin("GND")
    jumper(gnd, flat_hole(f"a{gnd_row}"), (30, 30, 30), via=(gnd[0], OY - 2.8 * S))
    # stray ceramic-disc capacitor lying beside the board (not inserted)
    cv2.circle(img, (1290, 790), 20, (40, 120, 235), -1)
    cv2.line(img, (1283, 806), (1275, 850), (170, 170, 175), 2)
    cv2.line(img, (1297, 806), (1306, 850), (170, 170, 175), 2)
    return img


def photoize(flat: np.ndarray) -> np.ndarray:
    out = cv2.warpPerspective(flat, WARP, (W, H), flags=cv2.INTER_AREA, borderValue=(55, 70, 90))
    yy, xx = np.mgrid[0:H, 0:W]
    light = 1.06 - 0.22 * ((xx - W * 0.35) ** 2 + (yy - H * 0.3) ** 2) / (W * W)
    out = np.clip(out.astype(np.float32) * light[..., None], 0, 255)
    rng = np.random.default_rng(11)
    out += rng.normal(0, 2.6, out.shape)
    out = cv2.GaussianBlur(np.clip(out, 0, 255).astype(np.uint8), (3, 3), 0.7)
    return out


def norm(px: float, py: float) -> list[float]:
    return [round(py / H * 1000, 1), round(px / W * 1000, 1)]  # [y, x]


def box(points: list[tuple[float, float]], pad: float = 16) -> list[float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    y0, x0, y1, x1 = min(ys) - pad, min(xs) - pad, max(ys) + pad, max(xs) + pad
    return [round(y0 / H * 1000, 1), round(x0 / W * 1000, 1), round(y1 / H * 1000, 1), round(x1 / W * 1000, 1)]


def proposals(gnd_row: int) -> dict:
    j = lambda v: v  # deterministic tiny offsets emulate a model's imprecision
    off = lambda p, dx, dy: (p[0] + dx, p[1] + dy)
    d9 = warp_pt(*header_pin("~9"))
    gnd = warp_pt(*header_pin("GND"))
    a10 = off(hole_px("a10"), 2.0, -1.5)
    gnd_end = off(hole_px(f"a{gnd_row}"), -1.5, 2.0)
    c10, c14 = off(hole_px("c10"), 1.0, 1.0), off(hole_px("c14"), -1.5, 0.5)
    d14, d15 = off(hole_px("d14"), 1.0, 1.5), off(hole_px("d15"), 0.5, -1.0)
    dome = warp_pt(*( (flat_hole("d14")[0] + flat_hole("d15")[0]) / 2, flat_hole("d14")[1] + 2.1 * S ))
    res_mid = warp_pt((flat_hole("c10")[0] + flat_hole("c14")[0]) / 2, flat_hole("c10")[1] - 0.9 * S)
    stray = warp_pt(1290, 790)
    ard = [warp_pt(HEADER_X0 - 6.5 * S, 40), warp_pt(HEADER_X0 + 18 * S, HEADER_Y + 1.3 * S)]
    return {
        "items": [
            {"kind": "arduino", "box_2d": box(ard, 6), "confidence": "high", "label_text": "ARDUINO UNO"},
            {
                "kind": "wire", "color": "green", "confidence": "high",
                "box_2d": box([d9, a10]),
                "leads": {"end_a": {"point": norm(*d9), "board_pin": "9"}, "end_b": {"point": norm(*a10)}},
            },
            {
                "kind": "resistor", "confidence": "high", "color_bands": ["red", "red", "brown", "gold"],
                "box_2d": box([res_mid, c10, c14], 22),
                "leads": {"1": {"point": norm(*c10)}, "2": {"point": norm(*c14)}},
            },
            {
                "kind": "led", "confidence": "medium", "color": "red",
                "box_2d": box([dome, d14, d15], 30),
                "orientation_note": "left lead (row 14) looks longer; flat rim on the right",
                "leads": {"anode": {"point": norm(*d14)}, "cathode": {"point": norm(*d15)}},
            },
            {
                "kind": "wire", "color": "black", "confidence": "medium",
                "box_2d": box([gnd, gnd_end]),
                "leads": {"end_a": {"point": norm(*gnd_end)}, "end_b": {"point": norm(*gnd), "board_pin": "GND"}},
            },
            {
                "kind": "capacitor", "confidence": "low", "box_2d": box([stray], 30),
                "description": "small orange disc beside the breadboard, possibly not inserted",
            },
        ],
        "obscured_regions": [],
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    corners = {name: hole_px(name) for name in ("a1", "a30", "j30", "j1")}
    specs = [
        ("seeded_wrong_row", 16, "SYNTHETIC TEST FIXTURE: ground jumper in row 16",
         "Synthetic render. The LED cathode is in row 15 but the ground jumper lands in row 16, so they are not connected."),
        ("corrected", 15, "SYNTHETIC TEST FIXTURE: ground jumper in row 15",
         "Synthetic render of the same circuit with the ground jumper moved to row 15."),
    ]
    for fid, gnd_row, title, desc in specs:
        d = OUT / fid
        d.mkdir(parents=True, exist_ok=True)
        photo = photoize(draw_scene(gnd_row))
        cv2.imwrite(str(d / "photo.jpg"), photo, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        (d / "proposals.json").write_text(json.dumps(proposals(gnd_row), indent=2) + "\n")
        (d / "meta.json").write_text(
            json.dumps(
                {
                    "id": fid, "title": title, "description": desc, "template_id": "uno_d9_led_220r",
                    "width": W, "height": H, "synthetic": True,
                    "landmarks": {k: {"x": round(v[0], 1), "y": round(v[1], 1)} for k, v in corners.items()},
                },
                indent=2,
            )
            + "\n"
        )
        print("wrote", d)


if __name__ == "__main__":
    main()
