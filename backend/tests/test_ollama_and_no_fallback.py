"""Local Gemma 4 (Ollama) provider, health reporting, and the no-silent-fallback guarantees.

Ollama is replaced by ``httpx.MockTransport``; no model runs in the test suite.
"""

import base64
import json
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.config import ConfigError, Settings
from app.image_processing import decode_bgr
from app.vision_provider import OllamaProvider, ProposeContext, ProviderError, get_provider, normalize

MODEL = "gemma4:e4b"

GOOD_JSON = json.dumps(
    {
        "items": [
            {"kind": "resistor", "confidence": "high", "color_bands": ["red", "red", "brown", "gold"],
             "box_2d": [400, 300, 450, 400], "leads": {"1": {"point": [430, 330]}, "2": {"point": [430, 390]}}}
        ],
        "obscured_regions": [],
    }
)


def ollama_settings(**kw) -> Settings:
    base = dict(vision_provider="ollama", ollama_host="http://ollama.test", ollama_model=MODEL, gemma_timeout_s=5.0)
    base.update(kw)
    return Settings(**base)


def make_ctx(template, catalog, fixture_photo, ok_calibration):
    jpeg, _ = fixture_photo("seeded_wrong_row")
    img = decode_bgr(jpeg)
    return ProposeContext("s1", template, catalog, jpeg, jpeg, img.shape[1], img.shape[0], ok_calibration, fixture_id=None), img


class FakeOllama:
    """Records requests and answers like Ollama's /api/tags, /api/ps and /api/generate."""

    def __init__(self, installed=(MODEL,), loaded=(), generate=None):
        self.requests: list[httpx.Request] = []
        self.installed, self.loaded, self.generate = installed, loaded, generate

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": n} for n in self.installed]})
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": n} for n in self.loaded]})
        if request.url.path == "/api/generate":
            if self.generate is not None:
                return self.generate(request)
            return httpx.Response(200, json={"response": GOOD_JSON, "done": True})
        return httpx.Response(404)

    @property
    def transport(self):
        return httpx.MockTransport(self)


# ----------------------------------------------------------------------------- config


def test_default_provider_is_local_ollama_with_a_gemma4_tag(monkeypatch):
    monkeypatch.delenv("VISION_PROVIDER", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    s = Settings()
    assert s.vision_provider == "ollama" and s.ollama_model.startswith("gemma4:")
    assert s.gemma_timeout_s == 60.0


@pytest.mark.parametrize("value", ["auto", "gemma", "openai", ""])
def test_auto_and_unknown_providers_are_rejected(monkeypatch, value):
    monkeypatch.setenv("VISION_PROVIDER", value)
    if value == "":
        assert Settings().vision_provider == "ollama"  # empty means "use the default", never demo
        return
    with pytest.raises(ConfigError, match="not supported"):
        Settings()


def test_get_provider_returns_exactly_the_configured_one():
    assert get_provider(ollama_settings()).info.name == "ollama"
    assert get_provider(replace(ollama_settings(), vision_provider="demo")).info.is_demo
    with pytest.raises(ProviderError, match="GEMINI_API_KEY"):
        get_provider(replace(ollama_settings(), vision_provider="gemini", gemini_api_key=""))


# ----------------------------------------------------------------------------- provider


def test_ollama_sends_one_image_one_request_and_parses(template, catalog, fixture_photo, ok_calibration):
    fake = FakeOllama()
    ctx, _ = make_ctx(template, catalog, fixture_photo, ok_calibration)
    raw = OllamaProvider(ollama_settings(), transport=fake.transport).propose(ctx)
    calls = [r for r in fake.requests if r.url.path == "/api/generate"]
    assert len(calls) == 1  # no retry loop
    body = json.loads(calls[0].content)
    assert body["model"] == MODEL and body["stream"] is False
    assert len(body["images"]) == 1 and base64.b64decode(body["images"][0]) == ctx.annotated_jpeg
    assert "untrusted" in body["system"]
    assert raw.items[0].kind == "resistor"


def test_ollama_not_running_is_an_unavailable_error_with_setup_steps(template, catalog, fixture_photo, ok_calibration):
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    ctx, _ = make_ctx(template, catalog, fixture_photo, ok_calibration)
    with pytest.raises(ProviderError) as e:
        OllamaProvider(ollama_settings(), transport=httpx.MockTransport(refuse)).propose(ctx)
    assert e.value.code == "unavailable" and "ollama pull gemma4:e4b" in e.value.message and "not running" in e.value.message


def test_ollama_model_missing_is_an_unavailable_error(template, catalog, fixture_photo, ok_calibration):
    fake = FakeOllama(generate=lambda r: httpx.Response(404, json={"error": "model 'gemma4:e4b' not found"}))
    ctx, _ = make_ctx(template, catalog, fixture_photo, ok_calibration)
    with pytest.raises(ProviderError) as e:
        OllamaProvider(ollama_settings(), transport=fake.transport).propose(ctx)
    assert e.value.code == "unavailable" and "not installed" in e.value.message and "ollama pull" in e.value.message


def test_ollama_timeout_is_reported_not_retried(template, catalog, fixture_photo, ok_calibration):
    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    fake = FakeOllama(generate=slow)
    ctx, _ = make_ctx(template, catalog, fixture_photo, ok_calibration)
    with pytest.raises(ProviderError) as e:
        OllamaProvider(ollama_settings(), transport=fake.transport).propose(ctx)
    assert e.value.code == "timeout" and "5 s" in e.value.message
    assert len([r for r in fake.requests if r.url.path == "/api/generate"]) == 1


def test_ollama_load_failure_and_garbage_are_errors(template, catalog, fixture_photo, ok_calibration):
    ctx, _ = make_ctx(template, catalog, fixture_photo, ok_calibration)
    oom = FakeOllama(generate=lambda r: httpx.Response(500, json={"error": "model requires more system memory"}))
    with pytest.raises(ProviderError, match="memory") as e:
        OllamaProvider(ollama_settings(), transport=oom.transport).propose(ctx)
    assert e.value.code == "unavailable"
    for text in ("", "no json here"):
        fake = FakeOllama(generate=lambda r, t=text: httpx.Response(200, json={"response": t}))
        with pytest.raises(ProviderError) as e:
            OllamaProvider(ollama_settings(), transport=fake.transport).propose(ctx)
        assert e.value.code == "bad_response"


def test_observations_carry_model_name_and_runtime(template, catalog, fixture_photo, ok_calibration):
    fake = FakeOllama()
    ctx, img = make_ctx(template, catalog, fixture_photo, ok_calibration)
    provider = OllamaProvider(ollama_settings(), transport=fake.transport)
    obs = normalize(provider.propose(ctx), ctx, img, "gemma", provider.info)
    assert obs and all(o.model_name == MODEL and "Ollama" in o.runtime and not o.is_demo_data for o in obs)
    assert all(o.status == "proposed" and o.source == "gemma" for o in obs)
    assert any(MODEL in e.note for e in obs[0].evidence)


def test_status_reports_reachable_installed_loaded():
    s = OllamaProvider(ollama_settings(), transport=FakeOllama(loaded=(MODEL,)).transport).status()
    assert (s.reachable, s.model_installed, s.model_loaded) == (True, True, True)
    s = OllamaProvider(ollama_settings(), transport=FakeOllama(installed=("llama3:8b",)).transport).status()
    assert (s.reachable, s.model_installed, s.model_loaded) == (True, False, False)

    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    s = OllamaProvider(ollama_settings(), transport=httpx.MockTransport(refuse)).status()
    assert s.reachable is False and s.error


# ----------------------------------------------------------------------------- API


@pytest.fixture()
def client():
    with TestClient(main.app) as c:
        yield c


def calibrated_demo_session(client):
    s = client.post("/api/sessions/demo", json={"template_id": "uno_d9_led_220r", "fixture_id": "seeded_wrong_row"}).json()
    cal = client.post(f"/api/sessions/{s['id']}/calibrate", json={"points": s["suggested_landmarks"]}).json()
    assert cal["status"] == "ok"
    return s["id"]


def test_unreachable_ollama_is_an_error_and_never_falls_back_to_demo(client, monkeypatch):
    sid = calibrated_demo_session(client)  # made while the suite's explicit demo setting is active
    monkeypatch.setattr(main, "settings", replace(main.settings, vision_provider="ollama", ollama_host="http://127.0.0.1:9"))
    r = client.post(f"/api/sessions/{sid}/analyze", json={})
    assert r.status_code == 503
    assert "Ollama is not running" in r.json()["detail"] and "ollama pull" in r.json()["detail"]
    obs = client.get(f"/api/sessions/{sid}/observations").json()
    assert not any(o["source"] == "demo" or o["is_demo_data"] for o in obs)  # nothing scripted was substituted
    assert not any(o["source"] == "gemma" for o in obs)
    # even a request that asks for the demo provider cannot switch it
    r = client.post(f"/api/sessions/{sid}/analyze", json={"provider": "demo"})
    assert r.status_code == 503


def test_gemini_without_key_is_an_error_not_demo(client, monkeypatch):
    sid = calibrated_demo_session(client)
    monkeypatch.setattr(main, "settings", replace(main.settings, vision_provider="gemini", gemini_api_key=""))
    r = client.post(f"/api/sessions/{sid}/analyze", json={})
    assert r.status_code == 503 and "GEMINI_API_KEY" in r.json()["detail"]
    assert not any(o["source"] == "demo" for o in client.get(f"/api/sessions/{sid}/observations").json())


def test_timeout_surfaces_as_503_without_fallback(client, monkeypatch):
    sid = calibrated_demo_session(client)
    cfg = replace(main.settings, vision_provider="ollama", ollama_host="http://ollama.test", ollama_model=MODEL)
    monkeypatch.setattr(main, "settings", cfg)

    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    fake = FakeOllama(generate=slow)
    monkeypatch.setattr(main, "get_provider", lambda s: OllamaProvider(s, transport=fake.transport))
    r = client.post(f"/api/sessions/{sid}/analyze", json={})
    assert r.status_code == 503 and "did not answer" in r.json()["detail"]
    assert len([x for x in fake.requests if x.url.path == "/api/generate"]) == 1


def test_real_provider_path_labels_observations_and_never_auto_confirms(client, monkeypatch):
    sid = calibrated_demo_session(client)
    cfg = replace(main.settings, vision_provider="ollama", ollama_host="http://ollama.test", ollama_model=MODEL)
    monkeypatch.setattr(main, "settings", cfg)
    fake = FakeOllama()
    monkeypatch.setattr(main, "get_provider", lambda s: OllamaProvider(s, transport=fake.transport))
    r = client.post(f"/api/sessions/{sid}/analyze", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["provider"]["name"] == "ollama" and body["provider"]["model"] == MODEL and not body["provider"]["is_demo"]
    assert not any("DEMO" in w for w in body["warnings"])
    model_obs = [o for o in body["observations"] if o["source"] == "gemma"]
    assert model_obs and all(o["model_name"] == MODEL and "Ollama" in o["runtime"] and o["status"] == "proposed" for o in model_obs)


def test_health_reports_ollama_state(client, monkeypatch):
    cfg = replace(main.settings, vision_provider="ollama", ollama_host="http://ollama.test", ollama_model=MODEL)
    monkeypatch.setattr(main, "settings", cfg)

    monkeypatch.setattr(main, "OllamaProvider", lambda s: OllamaProvider(s, transport=FakeOllama(loaded=(MODEL,)).transport))
    h = client.get("/api/health").json()
    assert (h["provider"], h["model"], h["demo_mode"]) == ("ollama", MODEL, False)
    assert h["reachable"] and h["model_installed"] and h["model_loaded"] and h["ready"]

    monkeypatch.setattr(main, "OllamaProvider", lambda s: OllamaProvider(s, transport=FakeOllama(installed=()).transport))
    h = client.get("/api/health").json()
    assert h["reachable"] and not h["model_installed"] and not h["ready"] and "ollama pull" in h["setup_hint"]

    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    monkeypatch.setattr(main, "OllamaProvider", lambda s: OllamaProvider(s, transport=httpx.MockTransport(refuse)))
    h = client.get("/api/health").json()
    assert not h["reachable"] and not h["ready"] and h["setup_hint"]


def test_synthetic_fixtures_exist_only_in_explicit_demo_mode(client, monkeypatch):
    assert client.get("/api/fixtures").json()  # suite runs with VISION_PROVIDER=demo
    monkeypatch.setattr(main, "settings", replace(main.settings, vision_provider="ollama"))
    assert client.get("/api/fixtures").json() == []
    r = client.post("/api/sessions/demo", json={"template_id": "uno_d9_led_220r", "fixture_id": "corrected"})
    assert r.status_code == 404
    assert all(f["synthetic"] for f in main.list_fixtures().values())
    assert all(f["title"].startswith("SYNTHETIC") for f in main.list_fixtures().values())
