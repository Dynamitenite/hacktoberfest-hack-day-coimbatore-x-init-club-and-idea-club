"""Deterministic expected-vs-observed comparison.

No model is consulted here. Findings come from:
  * the template's expected graph and explicit rules,
  * the catalog (component values), and
  * the observed graph built from user-confirmed observations only.
"""

from __future__ import annotations

import itertools

import networkx as nx

from .catalog import Catalog, decode_color_bands, format_ohms
from .circuit_graph import (
    BOARD_REF,
    ObservedBuild,
    build_expected_graph,
    build_observed_graph,
    describe_path,
    parse_strip,
    strips_in_component,
)
from .schemas import (
    CalibrationResult,
    CircuitTemplate,
    EdgeCheck,
    Evidence,
    Finding,
    Observation,
    Point,
    Report,
)

DISCLAIMER = (
    "Wirewise compares only the connections you confirmed in the photo against the selected template. "
    "It cannot see hidden or out-of-frame connections, component damage, poor contact, or mistakes in the catalog data, "
    "and it does not check voltages or currents. This is not a statement that the circuit is safe to power: "
    "review your wiring yourself before connecting power."
)

COMPARISON_METHOD = (
    "Deterministic graph comparison (NetworkX). Gemma only proposed observations; "
    "you confirmed them; template rules and catalog values decide every finding."
)


class _Ctx:
    def __init__(self, tpl, catalog, observations, calibration):
        self.tpl: CircuitTemplate = tpl
        self.catalog: Catalog = catalog
        self.obs: dict[str, Observation] = {o.id: o for o in observations}
        self.calibration = calibration
        self.grid: dict[str, tuple[float, float]] = {}
        self.pitch_px = 24.0
        if calibration and calibration.grid:
            self.grid = {h.hole: (h.x, h.y) for h in calibration.grid}
            if calibration.metrics:
                self.pitch_px = max(calibration.metrics.pitch_px_min, 6.0)
        self.counter = 0

    def next_id(self) -> str:
        self.counter += 1
        return f"f{self.counter}"

    def region(self, holes: list[str], obs_ids: list[str]) -> list[Point]:
        """Padded rectangle covering the given holes and the given observations' polygons."""
        pts: list[tuple[float, float]] = []
        pad = self.pitch_px * 0.9
        for h in holes:
            if h in self.grid:
                x, y = self.grid[h]
                pts += [(x - pad, y - pad), (x + pad, y + pad)]
        if not pts:
            for oid in obs_ids:
                o = self.obs.get(oid)
                if o:
                    pts += [(p.x, p.y) for p in o.bounding_box_or_polygon]
        if not pts:
            return []
        x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
        y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
        return [Point(x=x0, y=y0), Point(x=x1, y=y0), Point(x=x1, y=y1), Point(x=x0, y=y1)]


def _ev(*items: tuple[str, str]) -> list[Evidence]:
    return [Evidence(source=s, note=n) for s, n in items]  # type: ignore[arg-type]


def _label(tpl: CircuitTemplate, node_id: str) -> str:
    n = next((n for n in tpl.expected_nodes if n.id == node_id), None)
    return n.label if n else node_id


def _edge_text(tpl: CircuitTemplate, a: str, b: str) -> str:
    return f"{_label(tpl, a)} ⟷ {_label(tpl, b)}"


def _holes_of(obs_ids: list[str], ctx: _Ctx, g: nx.Graph, nodes: list[str]) -> list[str]:
    holes: set[str] = set()
    for n in nodes:
        if n in g:
            for nb in g.neighbors(n):
                if g.nodes[nb]["kind"] == "hole":
                    holes.add(nb.split(":", 1)[1])
    return sorted(holes)


def compare(
    session_id: str,
    tpl: CircuitTemplate,
    catalog: Catalog,
    observations: list[Observation],
    calibration: CalibrationResult | None,
) -> Report:
    ctx = _Ctx(tpl, catalog, observations, calibration)
    exp_g, exp_data = build_expected_graph(tpl)
    built: ObservedBuild = build_observed_graph(tpl, catalog, observations)
    G = built.graph

    findings: list[Finding] = []
    edge_checks: list[EdgeCheck] = []
    consumed_pins: set[str] = set()
    swapped: dict[str, str] = {}  # terminals already explained by a polarity finding

    pending = [o for o in observations if o.status == "proposed" and o.observation_type in ("component", "wire")]
    # Only proposals that map to a catalog part could still add a connection if confirmed.
    pending_effective_ids = [o.id for o in pending if o.candidate_part_or_endpoint.part_id]
    pending_ids = [o.id for o in pending]

    exp_net_of: dict[str, int] = {}
    for i, comp in enumerate(nx.connected_components(exp_g)):
        for n in comp:
            exp_net_of[n] = i

    def needs_obs(node_id: str) -> str | None:
        ref = node_id.split(".", 1)[0]
        return None if ref == BOARD_REF else ref

    # ------------------------------------------------------------------ 1. edges
    missing: list = []  # expected edges that are checkable but not observed
    edge_state: dict[str, EdgeCheck] = {}
    for e in tpl.expected_edges:
        refs = {r for r in (needs_obs(e.a), needs_obs(e.b)) if r}
        unconfirmed = sorted(r for r in refs if r not in built.component_obs)
        text = _edge_text(tpl, e.a, e.b)
        if unconfirmed:
            has_pending = any(
                (o.candidate_part_or_endpoint.template_ref in unconfirmed) for o in pending
            )
            why = (
                f"{', '.join(unconfirmed)} has a proposed observation that you have not confirmed yet."
                if has_pending
                else f"No confirmed observation of {', '.join(unconfirmed)} in the photo."
            )
            fid = ctx.next_id()
            findings.append(
                Finding(
                    id=fid, finding_type="ambiguous", severity="medium", status="NEEDS REVIEW",
                    title=f"Cannot check: {text}",
                    expected_connection=text, observed_connection=None,
                    expected_edge_ids=[e.id], rule_ids=[e.rule_id],
                    source_observation_ids=[o.id for o in pending if o.candidate_part_or_endpoint.template_ref in unconfirmed],
                    image_region=[],
                    explanation=f"{why} Confirm or correct the part (or add it manually) so this connection can be checked.",
                    evidence=_ev(("template", f"Rule {e.rule_id}")),
                )
            )
            edge_state[e.id] = EdgeCheck(edge_id=e.id, rule_id=e.rule_id, expected=text, state="NEEDS REVIEW", observed="Part not confirmed", finding_id=fid)
            continue
        if e.a in G and e.b in G and nx.has_path(G, e.a, e.b):
            observed = describe_path(G, e.a, e.b)
            edge_state[e.id] = EdgeCheck(edge_id=e.id, rule_id=e.rule_id, expected=text, state="MATCHES TEMPLATE", observed=observed)
        else:
            missing.append(e)

    # ------------------------------------------------------------ 2. polarity swap
    for inst in tpl.instances:
        part = catalog.part(inst.part_id)
        if not part or not part.polar or inst.ref not in built.component_obs:
            continue
        t1, t2 = (f"{inst.ref}.{t}" for t in part.terminal_names[:2])
        e1 = next((e for e in missing if t1 in (e.a, e.b)), None)
        e2 = next((e for e in missing if t2 in (e.a, e.b)), None)
        if not e1 or not e2:
            continue
        x1 = e1.b if e1.a == t1 else e1.a
        x2 = e2.b if e2.a == t2 else e2.a
        if t1 in G and t2 in G and x1 in G and x2 in G and nx.has_path(G, t1, x2) and nx.has_path(G, t2, x1):
            obs = built.component_obs[inst.ref]
            fid = ctx.next_id()
            holes = _holes_of([obs.id], ctx, G, [t1, t2])
            findings.append(
                Finding(
                    id=fid, finding_type="polarity_mismatch", severity="high", status="POSSIBLE MISMATCH",
                    title=f"{inst.ref} appears reversed",
                    expected_connection=f"{_edge_text(tpl, e1.a, e1.b)}; {_edge_text(tpl, e2.a, e2.b)}",
                    observed_connection=f"{_label(tpl, t1)} → {describe_path(G, t1, x2)}; {_label(tpl, t2)} → {describe_path(G, t2, x1)}",
                    expected_edge_ids=[e1.id, e2.id], rule_ids=["rule_led_polarity", e1.rule_id, e2.rule_id],
                    source_observation_ids=[obs.id], image_region=ctx.region(holes, [obs.id]),
                    explanation=(
                        f"In your confirmed observation, {inst.ref}'s {part.terminal_names[0]} sits on the net that should reach its "
                        f"{part.terminal_names[1]} and vice-versa. Swapping the two terminals would satisfy both template connections, so the part looks reversed."
                    ),
                    suggestion=f"Compare {inst.ref}'s lead lengths and flat edge with the catalog polarity cues, then re-check the terminals you confirmed.",
                    evidence=_ev(
                        ("catalog", f"{part.display_name}: polarity cues {part.orientation_metadata.get('polarity_cues') if part.orientation_metadata else 'n/a'}"),
                        ("template", "Rule rule_led_polarity"),
                        (obs.source, f"{obs.display_name} ({obs.status})"),
                    ),
                )
            )
            swapped.update({t1: t2, t2: t1})
            for e in (e1, e2):
                edge_state[e.id] = EdgeCheck(edge_id=e.id, rule_id=e.rule_id, expected=_edge_text(tpl, e.a, e.b), state="POSSIBLE MISMATCH", observed="Terminals appear swapped", finding_id=fid)
                missing.remove(e)

    # --------------------------------------------- 3. wrong pin / wrong row / missing
    for e in list(missing):
        text = _edge_text(tpl, e.a, e.b)
        board_end = next((n for n in (e.a, e.b) if n.startswith(f"{BOARD_REF}.")), None)
        other = e.b if board_end == e.a else e.a
        obs_ids: list[str] = []
        for n in (e.a, e.b):
            obs_ids += built.node_obs.get(n, [])
        finding: Finding | None = None

        # wrong pin: the non-board end is wired to a different board pin that the template does not use here
        if board_end and other in G:
            comp = nx.node_connected_component(G, other)
            stray = sorted(
                n for n in comp
                if G.nodes[n]["kind"] == "board_pin" and n != board_end
            )
            if stray:
                pin = stray[0].split(".", 1)[1]
                exp_pin = board_end.split(".", 1)[1]
                consumed_pins.update(stray)
                pin_obs = built.node_obs.get(stray[0], [])
                holes = _holes_of(pin_obs, ctx, G, [stray[0], other])
                fid = ctx.next_id()
                finding = Finding(
                    id=fid, finding_type="wrong_pin", severity="high", status="POSSIBLE MISMATCH",
                    title=f"{_label(tpl, other)} is wired to {pin}, not {exp_pin}",
                    expected_connection=text, observed_connection=f"{_label(tpl, other)} → {describe_path(G, other, stray[0])}",
                    expected_edge_ids=[e.id], rule_ids=[e.rule_id],
                    source_observation_ids=sorted(set(pin_obs + built.node_obs.get(other, []))),
                    image_region=ctx.region(holes, pin_obs),
                    explanation=f"The template requires {exp_pin}, but your confirmed wire lands on Arduino {pin}.",
                    suggestion=f"Move the wire end from {pin} to {exp_pin}, then update the observation.",
                    evidence=_ev(("catalog", "Pin names from the Arduino UNO R3 datasheet connector tables"), ("template", f"Rule {e.rule_id}"), ("user", "Wire endpoint confirmed by you")),
                )

        # wrong row: both ends are attached somewhere, but one strip off
        if finding is None and e.a in G and e.b in G:
            sa, sb = strips_in_component(G, e.a), strips_in_component(G, e.b)
            slip = None
            for x, y in itertools.product(sa, sb):
                (rx, sx), (ry, sy) = parse_strip(x), parse_strip(y)
                if sx == sy and abs(rx - ry) == 1:
                    slip = (x, y, "adjacent row")
                    break
                if rx == ry and sx != sy:
                    slip = (x, y, "opposite side of the centre channel")
                    break
            if slip:
                x, y, how = slip
                nodes_a = [n for n in nx.node_connected_component(G, e.a) if n.startswith("hole:")]
                nodes_b = [n for n in nx.node_connected_component(G, e.b) if n.startswith("hole:")]
                rx, _ = parse_strip(x); ry, _ = parse_strip(y)
                holes = sorted(
                    {n.split(":", 1)[1] for n in nodes_a if n.split(":", 1)[1][1:] == str(rx)}
                    | {n.split(":", 1)[1] for n in nodes_b if n.split(":", 1)[1][1:] == str(ry)}
                )
                oids = sorted(set(built.node_obs.get(e.a, []) + built.node_obs.get(e.b, [])))
                fid = ctx.next_id()
                finding = Finding(
                    id=fid, finding_type="wrong_row", severity="high", status="POSSIBLE MISMATCH",
                    title=f"Wire or lead on the wrong row: {text}",
                    expected_connection=text,
                    observed_connection=f"{_label(tpl, e.a)} is in {G.nodes[x]['label']}; {_label(tpl, e.b)} is in {G.nodes[y]['label']} ({how})",
                    expected_edge_ids=[e.id], rule_ids=[e.rule_id, "breadboard:strip_rule"],
                    source_observation_ids=oids, image_region=ctx.region(holes, oids),
                    explanation=(
                        f"These two terminals should share a breadboard strip, but your confirmed positions are one step apart ({how}). "
                        f"Breadboard rule: holes in the same row and side are joined; rows and the centre channel are not."
                    ),
                    suggestion="Move the lead or wire end to a hole in the same row strip, then re-run the check.",
                    evidence=_ev(("breadboard_model", "Connectivity: a–e and f–j joined per row; centre channel isolates them"), ("template", f"Rule {e.rule_id}"), ("user", "Endpoints confirmed by you")),
                )

        if finding is None:
            oids = sorted(set(obs_ids))
            absent = [_label(tpl, n) for n in (e.a, e.b) if n not in G]
            holes = _holes_of(oids, ctx, G, [n for n in (e.a, e.b) if n in G])
            fid = ctx.next_id()
            if absent:
                expl = f"No confirmed connection reaches {', '.join(absent)}."
            else:
                expl = "Both terminals are in your confirmed observations, but nothing confirmed joins them."
            finding = Finding(
                id=fid, finding_type="missing_connection", severity="high", status="POSSIBLE MISMATCH",
                title=f"Missing connection: {text}", expected_connection=text,
                observed_connection="No confirmed path between these terminals",
                expected_edge_ids=[e.id], rule_ids=[e.rule_id], source_observation_ids=oids,
                image_region=ctx.region(holes, oids), explanation=expl,
                suggestion="Add or move the wire or lead that should join these terminals, or confirm a wire you rejected by mistake.",
                evidence=_ev(("template", f"Rule {e.rule_id}")),
            )

        # Missing-type findings can still be resolved by unreviewed proposals.
        if pending_effective_ids:
            finding.status = "NEEDS REVIEW"
            finding.severity = "medium"
            finding.explanation += (
                f" {len(pending_effective_ids)} proposed observation(s) are still unreviewed and could change this result."
            )
            finding.source_observation_ids = sorted(set(finding.source_observation_ids + pending_effective_ids))
        findings.append(finding)
        edge_state[e.id] = EdgeCheck(
            edge_id=e.id, rule_id=e.rule_id, expected=text, state=finding.status,  # type: ignore[arg-type]
            observed=finding.observed_connection or "", finding_id=finding.id,
        )

    # ------------------------------------------------------ 4. unexpected connections
    for comp in nx.connected_components(G):
        terms = sorted(n for n in comp if G.nodes[n]["kind"] in ("terminal", "board_pin"))
        if len(terms) < 2:
            continue
        groups: dict[int, list[str]] = {}
        stray_pins = []
        for t in terms:
            if t in exp_net_of:
                # a reversed part is judged by the terminal it is physically acting as
                groups.setdefault(exp_net_of[swapped.get(t, t)], []).append(t)
            elif t.startswith(f"{BOARD_REF}.") and t not in consumed_pins:
                stray_pins.append(t)
        template_nodes = [t for t in terms if t in exp_net_of]
        bridges: list[tuple[str, str, str]] = []
        if len(groups) > 1:
            reps = [g[0] for g in groups.values()]
            for a, b in itertools.combinations(reps, 2):
                bridges.append((a, b, "bridge"))
        if stray_pins and template_nodes:
            for p in stray_pins:
                bridges.append((template_nodes[0], p, "stray"))
        for a, b, how in bridges:
            path = describe_path(G, a, b)
            oids = sorted({o for n in nx.shortest_path(G, a, b) for o in built.node_obs.get(n, [])})
            holes = _holes_of(oids, ctx, G, [n for n in nx.shortest_path(G, a, b) if G.nodes[n]["kind"] != "hole"])
            fid = ctx.next_id()
            if how == "bridge":
                title = f"Unexpected connection: {_label(tpl, a)} joins {_label(tpl, b)}"
                expl = "These terminals belong to different nets in the template, but your confirmed connections join them (for example through a shared strip or an extra wire)."
            else:
                title = f"Unexpected connection to {_label(tpl, b) if b not in exp_net_of else b}"
                expl = f"{b.split('.',1)[1]} is not part of this template's connections, yet a confirmed connection joins it to {_label(tpl, a)}."
            findings.append(
                Finding(
                    id=fid, finding_type="unexpected_connection", severity="high", status="POSSIBLE MISMATCH",
                    title=title, expected_connection="No connection between these terminals (rule_no_extra)",
                    observed_connection=path, rule_ids=["rule_no_extra"], source_observation_ids=oids,
                    image_region=ctx.region(holes, oids), explanation=expl,
                    suggestion="Check for a lead or wire sharing a strip with another part, or an extra jumper.",
                    evidence=_ev(("breadboard_model", "Holes in the same row side are joined"), ("template", "Rule rule_no_extra"), ("user", "Placement confirmed by you")),
                )
            )

    # ----------------------------------------------------------- 5. component values
    for rule in tpl.explicit_rules:
        if rule.type != "component_value" or not rule.instance:
            continue
        ref = rule.instance
        obs = built.component_obs.get(ref)
        if not obs:
            continue  # already reported as NEEDS REVIEW via the edges
        cand = obs.candidate_part_or_endpoint
        value = cand.value_ohms if cand.value_ohms is not None else decode_color_bands(cand.color_bands)
        expected = float(rule.expected["value"]) if rule.expected else None
        if value is None:
            fid = ctx.next_id()
            findings.append(
                Finding(
                    id=fid, finding_type="ambiguous", severity="medium", status="NEEDS REVIEW",
                    title=f"{ref} value not confirmed", expected_connection=None, observed_connection=None,
                    rule_ids=[rule.id], source_observation_ids=[obs.id], image_region=ctx.region([], [obs.id]),
                    explanation=f"{ref} should be {format_ohms(expected)} but no value or colour bands were confirmed. Enter the colour bands you read from the part.",
                    evidence=_ev(("template", f"Rule {rule.id}")),
                )
            )
        elif expected is not None and abs(value - expected) > 1e-6:
            fid = ctx.next_id()
            findings.append(
                Finding(
                    id=fid, finding_type="value_mismatch", severity="medium", status="POSSIBLE MISMATCH",
                    title=f"{ref} value differs: {format_ohms(value)} vs {format_ohms(expected)}",
                    expected_connection=f"{ref} = {format_ohms(expected)}", observed_connection=f"{ref} = {format_ohms(value)} (confirmed)",
                    rule_ids=[rule.id], source_observation_ids=[obs.id], image_region=ctx.region([], [obs.id]),
                    explanation=(
                        f"The template lists a {format_ohms(expected)} resistor for {ref}. "
                        f"Your confirmed value is {format_ohms(value)} "
                        f"({'from colour bands ' + '-'.join(cand.color_bands) if cand.color_bands and cand.value_ohms is None else 'as entered'}). "
                        "Wirewise does not judge whether the other value is acceptable: it only reports the difference."
                    ),
                    suggestion="Verify the colour bands against the part, or choose a different template.",
                    evidence=_ev(("catalog", "Nominal value from IEC 60062 colour code"), ("template", f"Rule {rule.id}"), (obs.source, f"{obs.display_name} ({obs.status})")),
                )
            )

    # ------------------------------------------------- 6. NOT CHECKED / NEEDS REVIEW extras
    for issue in built.issues:
        fid = ctx.next_id()
        findings.append(
            Finding(
                id=fid, finding_type="not_checked", severity="low", status="NOT CHECKED",
                title="Outside MVP support" if issue.kind != "bad_hole" else "Unusable endpoint",
                explanation=issue.message, source_observation_ids=issue.observation_ids,
                image_region=ctx.region([], issue.observation_ids),
                evidence=_ev(("catalog", "Only catalog-verified parts, pins and the modelled breadboard strips are checked")),
            )
        )

    for o in observations:
        if o.observation_type == "obscured_region" and o.status in ("confirmed", "corrected"):
            findings.append(
                Finding(
                    id=ctx.next_id(), finding_type="ambiguous", severity="medium", status="NEEDS REVIEW",
                    title="Obscured or unclear area", explanation=(o.candidate_part_or_endpoint.description or "An area of the photo is too unclear to inspect.")
                    + " Retake the photo or move what covers it.",
                    source_observation_ids=[o.id], image_region=ctx.region([], [o.id]),
                    evidence=_ev((o.source, "Flagged and confirmed as unclear")),
                )
            )

    if pending:
        findings.append(
            Finding(
                id=ctx.next_id(), finding_type="ambiguous", severity="medium", status="NEEDS REVIEW",
                title=f"{len(pending)} proposed observation(s) not reviewed",
                explanation="Proposed observations are never treated as facts. Confirm, correct or reject each one so the check covers everything in the photo.",
                source_observation_ids=pending_ids, image_region=[],
                evidence=_ev(("user", "Human confirmation is required")),
            )
        )

    if calibration is None or calibration.status != "ok":
        findings.append(
            Finding(
                id=ctx.next_id(), finding_type="ambiguous", severity="medium", status="NEEDS REVIEW",
                title="Grid calibration is not verified",
                explanation=(
                    "The grid alignment was low-confidence or accepted by hand, so hole positions inferred from the photo may be off."
                    if calibration else "The photo has not been calibrated."
                ),
                evidence=_ev(("opencv", "Calibration check")),
            )
        )

    # Standing limits: always listed so the report never reads as a safety verdict.
    standing = [
        ("Electrical ratings", "No voltage or current limits are stored in the catalog for these parts, so none are checked."),
        ("Breadboard power rails", "Rails are not modelled for this breadboard model; any connection to a rail is NOT CHECKED."),
        ("Hidden or out-of-frame details", "Connections under components, behind the board, or outside the photo cannot be verified."),
    ]
    for title, text in standing:
        findings.append(
            Finding(
                id=ctx.next_id(), finding_type="not_checked", severity="info", status="NOT CHECKED",
                title=title, explanation=text, evidence=_ev(("catalog", "Scope of the supported template")),
            )
        )

    # ---------------------------------------------------------------- 7. roll-up
    for e in tpl.expected_edges:
        edge_checks.append(edge_state[e.id])
    mismatches = [f for f in findings if f.status == "POSSIBLE MISMATCH"]
    reviews = [f for f in findings if f.status == "NEEDS REVIEW"]
    notchecked = [f for f in findings if f.status == "NOT CHECKED"]
    matched = sum(1 for c in edge_checks if c.state == "MATCHES TEMPLATE")

    if mismatches:
        overall = "POSSIBLE MISMATCH"
        headline = f"Possible mismatch: {len(mismatches)} confirmed difference(s) from the template."
    elif reviews:
        overall = "NEEDS REVIEW"
        headline = f"Needs review: {len(reviews)} item(s) are ambiguous or unconfirmed, so a reliable check is not possible yet."
    else:
        overall = "MATCHES TEMPLATE"
        headline = "The visible, confirmed connections match this template. Hidden details and electrical limits are not checked."

    order = {"POSSIBLE MISMATCH": 0, "NEEDS REVIEW": 1, "NOT CHECKED": 2, "MATCHES TEMPLATE": 3}
    findings.sort(key=lambda f: (order[f.status], {"high": 0, "medium": 1, "low": 2, "info": 3}[f.severity]))

    return Report(
        session_id=session_id,
        template_id=tpl.id,
        overall_status=overall,  # type: ignore[arg-type]
        headline=headline,
        findings=findings,
        edge_checks=edge_checks,
        expected_graph=exp_data,
        observed_graph=built.data,
        connections=built.connections,
        counts={
            "edges_total": len(tpl.expected_edges),
            "edges_matched": matched,
            "possible_mismatch": len(mismatches),
            "needs_review": len(reviews),
            "not_checked": len(notchecked),
        },
        disclaimer=DISCLAIMER,
        comparison_method=COMPARISON_METHOD,
    )
