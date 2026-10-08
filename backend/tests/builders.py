"""Helpers to construct confirmed observations for tests and fixtures."""
from app.schemas import Candidate, Endpoint, Observation, Point

SID = "sess-test"


def hole(h):
    return Endpoint(kind="breadboard_hole", hole=h)


def pin(p):
    return Endpoint(kind="board_pin", board_pin=p)


def comp(oid, part_id, ref, endpoints, status="confirmed", source="gemma", **kw):
    return Observation(
        id=oid, image_session_id=SID, observation_type="component",
        candidate_part_or_endpoint=Candidate(part_id=part_id, template_ref=ref, endpoints=endpoints, **kw),
        bounding_box_or_polygon=[Point(x=10, y=10), Point(x=40, y=10), Point(x=40, y=40), Point(x=10, y=40)],
        confidence_label="high", source=source, status=status, display_name=ref,
    )


def wire(oid, a, b, status="confirmed", source="gemma"):
    return Observation(
        id=oid, image_session_id=SID, observation_type="wire",
        candidate_part_or_endpoint=Candidate(part_id="jumper_wire", endpoints={"end_a": a, "end_b": b}),
        bounding_box_or_polygon=[Point(x=50, y=50), Point(x=90, y=50), Point(x=90, y=90), Point(x=50, y=90)],
        confidence_label="high", source=source, status=status, display_name=f"Wire {oid}",
    )


def correct_circuit():
    """D9 -> a10 | R1 c10..c14 | LED anode d14 cathode d15 | a15 -> GND."""
    return [
        wire("w1", pin("D9"), hole("a10")),
        comp("r1", "resistor_220r", "R1", {"1": hole("c10"), "2": hole("c14")}, color_bands=["red", "red", "brown"]),
        comp("led1", "led_5mm_red", "LED1", {"anode": hole("d14"), "cathode": hole("d15")}),
        wire("w2", hole("a15"), pin("GND")),
    ]


def seeded_mismatch():
    """GND wire lands on row 16 instead of row 15."""
    obs = correct_circuit()
    obs[3] = wire("w2", hole("a16"), pin("GND"))
    return obs
