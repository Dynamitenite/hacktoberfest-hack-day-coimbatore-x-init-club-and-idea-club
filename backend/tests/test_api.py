"""HTTP-level flow. The suite runs with VISION_PROVIDER=demo set explicitly in conftest (no model, no network)."""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def demo_session(client, fixture="seeded_wrong_row"):
    r = client.post("/api/sessions/demo", json={"template_id": "uno_d9_led_220r", "fixture_id": fixture})
    assert r.status_code == 200, r.text
    return r.json()


def calibrated(client, fixture="seeded_wrong_row"):
    s = demo_session(client, fixture)
    cal = client.post(f"/api/sessions/{s['id']}/calibrate", json={"points": s["suggested_landmarks"]}).json()
    assert cal["status"] == "ok"
    return s["id"]


def review_all(client, sid, obs):
    for o in obs:
        if o["observation_type"] in ("component", "wire"):
            action = "reject" if o["candidate_part_or_endpoint"]["part_id"] is None else "confirm"
            assert client.patch(f"/api/sessions/{sid}/observations/{o['id']}", json={"action": action}).status_code == 200


def test_health_reports_demo_mode_explicitly(client):
    h = client.get("/api/health").json()
    assert h["provider"] == "demo" and h["demo_mode"] is True and h["model"] is None and h["ready"] is True and h["model_loaded"] is False
    assert "no model" in h["message"].lower()


def test_unsupported_template_is_a_clear_404(client):
    r = client.post("/api/sessions/demo", json={"template_id": "esp32_motor", "fixture_id": "corrected"})
    assert r.status_code == 404 and "Unsupported circuit" in r.json()["detail"]


def test_full_demo_flow_seeded_then_corrected(client):
    sid = calibrated(client)
    an = client.post(f"/api/sessions/{sid}/analyze", json={}).json()
    assert an["provider"]["is_demo"] is True and any("DEMO MODE" in w for w in an["warnings"])
    assert all(o["status"] in ("proposed", "confirmed") for o in an["observations"])  # only the user-placed outline is pre-confirmed
    # before any review nothing can pass
    assert client.get(f"/api/sessions/{sid}/report").json()["overall_status"] != "MATCHES TEMPLATE"
    review_all(client, sid, an["observations"])
    rep = client.get(f"/api/sessions/{sid}/report").json()
    assert rep["overall_status"] == "POSSIBLE MISMATCH"
    f = next(f for f in rep["findings"] if f["status"] == "POSSIBLE MISMATCH")
    assert f["finding_type"] == "wrong_row" and len(f["image_region"]) == 4

    # correct the ground wire in the UI
    wire = next(o for o in an["observations"] if o["display_name"].startswith("Black"))
    cand = wire["candidate_part_or_endpoint"]
    cand["endpoints"]["end_a"] = {"kind": "breadboard_hole", "hole": "A15"}
    patched = client.patch(f"/api/sessions/{sid}/observations/{wire['id']}", json={"action": "correct", "candidate": cand}).json()
    assert patched["status"] == "corrected" and patched["source"] == "user"
    assert patched["original_candidate"]["endpoints"]["end_a"]["hole"] == "a16"
    assert client.get(f"/api/sessions/{sid}/report").json()["overall_status"] == "MATCHES TEMPLATE"


def test_corrected_photo_matches_after_review(client):
    sid = calibrated(client, "corrected")
    an = client.post(f"/api/sessions/{sid}/analyze", json={}).json()
    review_all(client, sid, an["observations"])
    rep = client.get(f"/api/sessions/{sid}/report").json()
    assert rep["overall_status"] == "MATCHES TEMPLATE" and "safe" not in rep["headline"].lower()


def test_analyze_requires_calibration_and_blocks_low_confidence(client):
    s = demo_session(client)
    assert client.post(f"/api/sessions/{s['id']}/analyze", json={}).status_code == 409
    shifted = {k: {"x": v["x"] + 14, "y": v["y"] + 11} for k, v in s["suggested_landmarks"].items()}
    cal = client.post(f"/api/sessions/{s['id']}/calibrate", json={"points": shifted}).json()
    assert cal["status"] == "low_confidence"
    blocked = client.post(f"/api/sessions/{s['id']}/analyze", json={})
    assert blocked.status_code == 409 and "low-confidence" in blocked.json()["detail"]
    ok = client.post(f"/api/sessions/{s['id']}/analyze", json={"accept_unverified_calibration": True})
    assert ok.status_code == 200
    # an accepted-but-unverified grid can never yield a clean pass
    sid = s["id"]
    review_all(client, sid, ok.json()["observations"])
    assert client.get(f"/api/sessions/{sid}/report").json()["overall_status"] != "MATCHES TEMPLATE"


def test_demo_provider_refuses_a_user_photo(client):
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (90, 90, 90)).save(buf, format="PNG")
    r = client.post("/api/sessions", data={"template_id": "uno_d9_led_220r"}, files={"file": ("mine.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200
    sid = r.json()["id"]
    pts = {"a1": {"x": 100, "y": 100}, "a30": {"x": 700, "y": 100}, "j30": {"x": 700, "y": 400}, "j1": {"x": 100, "y": 400}}
    client.post(f"/api/sessions/{sid}/calibrate", json={"points": pts})
    r = client.post(f"/api/sessions/{sid}/analyze", json={"accept_unverified_calibration": True})
    assert r.status_code == 400 and "bundled synthetic test photos" in r.json()["detail"]


def test_upload_validation_errors(client):
    r = client.post("/api/sessions", data={"template_id": "uno_d9_led_220r"}, files={"file": ("x.gif", b"GIF89a", "image/gif")})
    assert r.status_code == 415
    r = client.post("/api/sessions", data={"template_id": "uno_d9_led_220r"}, files={"file": ("x.png", b"junk", "image/png")})
    assert r.status_code == 422


def test_corrections_are_validated_against_the_catalog(client):
    sid = calibrated(client)
    an = client.post(f"/api/sessions/{sid}/analyze", json={}).json()
    wire = next(o for o in an["observations"] if o["observation_type"] == "wire")
    cand = wire["candidate_part_or_endpoint"]
    cand["endpoints"]["end_a"] = {"kind": "breadboard_hole", "hole": "z99"}
    assert client.patch(f"/api/sessions/{sid}/observations/{wire['id']}", json={"action": "correct", "candidate": cand}).status_code == 422
    cand["endpoints"]["end_a"] = {"kind": "board_pin", "board_pin": "A0"}
    assert client.patch(f"/api/sessions/{sid}/observations/{wire['id']}", json={"action": "correct", "candidate": cand}).status_code == 422


def test_session_is_in_memory_and_deletable_and_save_is_explicit(client):
    sid = calibrated(client)
    from app.main import db

    before = len(db.list_projects())
    assert client.get(f"/api/sessions/{sid}/image").status_code == 200
    assert len(db.list_projects()) == before  # nothing persisted yet
    saved = client.post(f"/api/sessions/{sid}/save", json={"name": "demo run"}).json()
    assert len(db.list_projects()) == before + 1
    assert client.delete(f"/api/projects/{saved['id']}").status_code == 204
    assert client.delete(f"/api/sessions/{sid}").status_code == 204
    assert client.get(f"/api/sessions/{sid}").status_code == 404
