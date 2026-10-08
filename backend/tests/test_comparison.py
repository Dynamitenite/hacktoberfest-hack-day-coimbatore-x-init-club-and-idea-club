"""Deterministic comparison behaviour, including the invariants the product promises."""

import json

from app.comparison import compare
from builders import comp, correct_circuit, hole, pin, seeded_mismatch, wire


def run(template, catalog, obs, cal=None):
    return compare("s", template, catalog, obs, cal)


def types(report, status=None):
    return [f.finding_type for f in report.findings if status is None or f.status == status]


def test_correct_circuit_matches_template(template, catalog, ok_calibration):
    r = run(template, catalog, correct_circuit(), ok_calibration)
    assert r.overall_status == "MATCHES TEMPLATE"
    assert r.counts["edges_matched"] == 3 and r.counts["possible_mismatch"] == 0
    assert all(c.state == "MATCHES TEMPLATE" for c in r.edge_checks)


def test_seeded_wrong_row_is_found_with_region_and_provenance(template, catalog, ok_calibration):
    r = run(template, catalog, seeded_mismatch(), ok_calibration)
    assert r.overall_status == "POSSIBLE MISMATCH"
    f = next(f for f in r.findings if f.status == "POSSIBLE MISMATCH")
    assert f.finding_type == "wrong_row"
    assert f.expected_edge_ids == ["e_gnd"] and "rule_gnd" in f.rule_ids
    assert set(f.source_observation_ids) >= {"w2", "led1"}
    assert len(f.image_region) == 4  # rectangle around the two rows, from the calibrated grid
    assert "row 16" in f.observed_connection and "row 15" in f.observed_connection


def test_wrong_pin_d8_instead_of_d9(template, catalog, ok_calibration):
    obs = correct_circuit()
    obs[0] = wire("w1", pin("D8"), hole("a10"))
    r = run(template, catalog, obs, ok_calibration)
    f = next(f for f in r.findings if f.status == "POSSIBLE MISMATCH")
    assert f.finding_type == "wrong_pin" and "D8" in f.title and "D9" in f.title
    # the stray D8 connection is explained by wrong_pin, not double-reported
    assert "unexpected_connection" not in types(r)


def test_reversed_led_is_reported_as_polarity_mismatch_once(template, catalog, ok_calibration):
    obs = correct_circuit()
    obs[2] = comp("led1", "led_5mm_red", "LED1", {"anode": hole("d15"), "cathode": hole("d14")})
    r = run(template, catalog, obs, ok_calibration)
    mism = [f for f in r.findings if f.status == "POSSIBLE MISMATCH"]
    assert [f.finding_type for f in mism] == ["polarity_mismatch"]
    assert set(mism[0].expected_edge_ids) == {"e_led", "e_gnd"}


def test_resistor_leads_in_same_row_is_unexpected_connection(template, catalog, ok_calibration):
    obs = correct_circuit()
    obs[1] = comp("r1", "resistor_220r", "R1", {"1": hole("c10"), "2": hole("d10")}, color_bands=["red", "red", "brown"])
    r = run(template, catalog, obs, ok_calibration)
    assert "unexpected_connection" in types(r, "POSSIBLE MISMATCH")


def test_wire_from_gnd_to_resistor_row_is_unexpected(template, catalog, ok_calibration):
    obs = correct_circuit() + [wire("w3", pin("GND"), hole("b10"))]
    r = run(template, catalog, obs, ok_calibration)
    assert r.overall_status == "POSSIBLE MISMATCH"
    assert "unexpected_connection" in types(r)


def test_resistor_value_mismatch_uses_catalog_colour_code(template, catalog, ok_calibration):
    obs = correct_circuit()
    obs[1] = comp("r1", "resistor_220r", "R1", {"1": hole("c10"), "2": hole("c14")}, color_bands=["brown", "black", "brown"])  # 100 ohm
    r = run(template, catalog, obs, ok_calibration)
    f = next(f for f in r.findings if f.finding_type == "value_mismatch")
    assert "100 Ω" in f.title and "220 Ω" in f.title and f.status == "POSSIBLE MISMATCH"


def test_resistor_without_value_needs_review_not_pass(template, catalog, ok_calibration):
    obs = correct_circuit()
    obs[1] = comp("r1", "resistor_220r", "R1", {"1": hole("c10"), "2": hole("c14")})
    r = run(template, catalog, obs, ok_calibration)
    assert r.overall_status == "NEEDS REVIEW"


def test_missing_ground_wire_is_missing_connection(template, catalog, ok_calibration):
    obs = correct_circuit()[:3]
    r = run(template, catalog, obs, ok_calibration)
    f = next(f for f in r.findings if f.status == "POSSIBLE MISMATCH")
    assert f.finding_type == "missing_connection" and "GND" in f.title


# ------------------------------------------------------------------ invariants


def test_proposed_observations_never_create_edges(template, catalog, ok_calibration):
    obs = correct_circuit()
    for o in obs:
        o.status = "proposed"
    r = run(template, catalog, obs, ok_calibration)
    assert r.observed_graph.edges == []
    assert r.overall_status != "MATCHES TEMPLATE"
    assert all(c.state != "MATCHES TEMPLATE" for c in r.edge_checks)


def test_rejected_observations_never_create_edges(template, catalog, ok_calibration):
    obs = correct_circuit()
    obs[3].status = "rejected"
    r = run(template, catalog, obs, ok_calibration)
    assert r.overall_status == "POSSIBLE MISMATCH"
    assert not any("w2" in e.observation_ids for e in r.observed_graph.edges)


def test_unreviewed_proposal_downgrades_missing_to_needs_review(template, catalog, ok_calibration):
    obs = correct_circuit()
    obs[3].status = "proposed"  # GND wire not yet reviewed
    r = run(template, catalog, obs, ok_calibration)
    assert r.overall_status == "NEEDS REVIEW"
    assert not [f for f in r.findings if f.status == "POSSIBLE MISMATCH"]


def test_unconfirmed_component_is_needs_review(template, catalog, ok_calibration):
    obs = correct_circuit()
    obs[1].status = "proposed"
    r = run(template, catalog, obs, ok_calibration)
    assert r.overall_status == "NEEDS REVIEW"


def test_unverified_calibration_prevents_a_clean_pass(template, catalog, ok_calibration):
    r = run(template, catalog, correct_circuit(), None)
    assert r.overall_status == "NEEDS REVIEW"


def test_power_rail_endpoint_is_not_checked_not_assumed(template, catalog, ok_calibration):
    obs = correct_circuit()
    obs[3] = wire("w2", hole("a15"), type(hole("a1"))(kind="power_rail", note="blue rail"))
    r = run(template, catalog, obs, ok_calibration)
    assert any(f.status == "NOT CHECKED" and "power rail" in f.explanation for f in r.findings)
    assert r.overall_status == "POSSIBLE MISMATCH"  # the ground return is still not demonstrated


def test_unsupported_board_pin_is_not_checked(template, catalog, ok_calibration):
    obs = correct_circuit() + [wire("w9", pin("A0"), hole("j1"))]
    r = run(template, catalog, obs, ok_calibration)
    assert any(f.status == "NOT CHECKED" and "A0" in f.explanation for f in r.findings)


def test_report_never_claims_safe(template, catalog, ok_calibration):
    for obs in (correct_circuit(), seeded_mismatch()):
        r = run(template, catalog, obs, ok_calibration)
        assert "safe to power" in r.disclaimer.lower() and "not a statement" in r.disclaimer.lower()
        body = json.dumps(r.model_dump(mode="json", exclude={"disclaimer"})).lower()
        assert "safe" not in body
        assert r.overall_status in {"MATCHES TEMPLATE", "POSSIBLE MISMATCH", "NEEDS REVIEW"}


def test_every_observed_node_and_edge_has_provenance(template, catalog, ok_calibration):
    r = run(template, catalog, correct_circuit(), ok_calibration)
    for n in r.observed_graph.nodes:
        assert n.sources, n.id
    for e in r.observed_graph.edges:
        assert e.sources, e.id
    for e in r.observed_graph.edges:
        if e.kind in ("wire", "component_lead"):
            assert e.observation_ids
    assert any(s.startswith("gemma:confirmed") for n in r.observed_graph.nodes for s in n.sources)


def test_finding_links_to_rule_and_expected_edge(template, catalog, ok_calibration):
    r = run(template, catalog, seeded_mismatch(), ok_calibration)
    f = next(f for f in r.findings if f.status == "POSSIBLE MISMATCH")
    assert all(template.rule(rid) or rid.startswith("breadboard:") for rid in f.rule_ids)
    assert all(eid in {e.id for e in template.expected_edges} for eid in f.expected_edge_ids)
