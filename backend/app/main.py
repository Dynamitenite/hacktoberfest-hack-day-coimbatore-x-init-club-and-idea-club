"""Wirewise API (FastAPI).

Inspection aid only: nothing here controls hardware, powers a board or talks to
a device over USB, serial, Bluetooth or the network.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import catalog as cat_mod
from .catalog import hole_name, load_catalog, load_templates, normalize_board_pin, parse_hole
from .comparison import compare
from .config import settings
from .image_processing import (
    ALLOWED_MIME,
    UploadError,
    annotate_for_model,
    calibrate,
    decode_bgr,
    encode_jpeg,
    rectify,
    suggest_landmarks,
    validate_and_normalize,
)
from .schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    CalibrationRequest,
    CalibrationResult,
    Candidate,
    Endpoint,
    Evidence,
    ImageSession,
    NewObservationRequest,
    Observation,
    ObservationAction,
    Point,
    ProviderInfo,
    RectifiedInfo,
    Report,
    utcnow,
)
from .storage import Database, SessionState, SessionStore
from .vision_provider import OllamaProvider, ProposeContext, ProviderError, get_provider, list_fixtures, normalize

# Real photos of the physical build, shipped in the repo-root fixtures/ folder. Only files that exist are offered.
SAMPLE_PHOTOS = {
    "correct": ("correct.jpg", "Real photo: correct build", "The build wired as the template describes."),
    "wrong_wire": ("wrong_wire.jpg", "Real photo: seeded wiring mistake", "The same build with one deliberate wiring mistake."),
    "blurry": ("blurry.jpg", "Real photo: blurry", "A deliberately blurry photo. Wirewise should ask for review rather than pass it."),
}

PX_PER_PITCH = 28
MARGIN_PITCH = 2.0

store = SessionStore(settings.session_ttl_minutes)
db: Database


@asynccontextmanager
async def lifespan(_: FastAPI):
    global db
    load_catalog()
    load_templates()  # fails fast if a template references anything outside the catalog
    db = Database(settings)
    yield


app = FastAPI(
    title="Wirewise API",
    version="0.1.0",
    description="Compare a breadboard photo with an intended circuit. Inspection aid only; never claims a circuit is safe to power.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- helpers


def _state(sid: str) -> SessionState:
    state = store.get(sid)
    if not state:
        raise HTTPException(404, "Session not found or expired. Upload the photo again.")
    return state


def _tpl(template_id: str):
    tpl = load_templates().get(template_id)
    if not tpl:
        raise HTTPException(
            404,
            f"Unsupported circuit '{template_id}'. Wirewise only checks the preconfigured templates: {', '.join(load_templates())}.",
        )
    return tpl


def _new_session(
    template_id: str, jpeg: bytes, width: int, height: int, fixture_id: str | None = None, synthetic: bool = False
) -> SessionState:
    sid = "ses_" + uuid.uuid4().hex[:10]
    session = ImageSession(
        id=sid,
        circuit_template_id=template_id,
        image_reference=f"memory://{sid}",  # in-memory only unless the user saves the project
        width=width,
        height=height,
        fixture_id=fixture_id,
        synthetic=synthetic,
    )
    state = store.create(session, jpeg)
    if fixture_id:
        meta = list_fixtures()[fixture_id]
        session.suggested_landmarks = {k: Point(**v) for k, v in meta["landmarks"].items()}
    else:
        session.suggested_landmarks = suggest_landmarks(decode_bgr(jpeg))
    return state


def _validate_candidate(c: Candidate, template_id: str, *, require_part: bool = True) -> Candidate:
    tpl, catalog = _tpl(template_id), load_catalog()
    board = catalog.breadboards[tpl.breadboard_model_id]
    board_part = catalog.parts[tpl.supported_board_id]
    if c.part_id is not None and c.part_id not in catalog.parts:
        raise HTTPException(422, f"Part '{c.part_id}' is not in the supported catalog.")
    if c.template_ref is not None:
        inst = tpl.instance(c.template_ref)
        if inst is None or (c.part_id and inst.part_id != c.part_id):
            raise HTTPException(422, f"'{c.template_ref}' is not a {c.part_id} in this template.")
    part = catalog.part(c.part_id)
    for term, ep in c.endpoints.items():
        if part and term not in part.terminal_names:
            raise HTTPException(422, f"'{term}' is not a terminal of {part.display_name}. Use: {', '.join(part.terminal_names)}.")
        if ep.kind == "breadboard_hole":
            parsed = parse_hole(ep.hole, board)
            if not parsed:
                raise HTTPException(422, f"'{ep.hole}' is not a hole on this breadboard (columns a-j, rows 1-{board.rows}).")
            ep.hole = hole_name(*parsed)
        elif ep.kind == "board_pin":
            pin = normalize_board_pin(ep.board_pin, board_part)
            if not pin:
                raise HTTPException(
                    422,
                    f"'{ep.board_pin}' is not a verified pin for {board_part.display_name}. Verified pins: {', '.join(board_part.terminal_names)}.",
                )
            ep.board_pin = pin
    if c.value_ohms is not None and c.value_ohms <= 0:
        raise HTTPException(422, "Resistance must be positive.")
    return c


def _calibrated(state: SessionState) -> CalibrationResult:
    cal = state.session.calibration
    if not cal or cal.status == "failed" or not cal.homography:
        raise HTTPException(409, "Calibrate the photo first: place the four corner landmarks.")
    return cal


# --------------------------------------------------------------------------- meta


def _provider_health() -> dict:
    """Active provider, model, and whether the model is reachable and loaded. Never runs inference."""
    name = settings.vision_provider
    base = {
        "provider": name,
        "model": None,
        "runtime": None,
        "demo_mode": name == "demo",
        "reachable": False,
        "model_installed": False,
        "model_loaded": False,
        "ready": False,
        "message": "",
        "setup_hint": None,
    }
    if name == "demo":
        base.update(
            runtime="demo (no model)",
            ready=True,  # scripted fixtures are always available; the UI shows the DEMO banner instead of a model status
            message="DEMO MODE: no model is analyzing this image. Scripted synthetic fixtures only.",
        )
        return base
    if name == "ollama":
        provider = OllamaProvider(settings)
        st = provider.status()
        base.update(model=settings.ollama_model, runtime=provider.info.runtime, reachable=st.reachable,
                    model_installed=st.model_installed, model_loaded=st.model_loaded)
        if not st.reachable:
            base.update(message=st.error or "Ollama is not reachable.", setup_hint=provider.setup_hint)
        elif not st.model_installed:
            base.update(message=f"Ollama is running but model '{settings.ollama_model}' is not installed.", setup_hint=provider.setup_hint)
        elif not st.model_loaded:
            base.update(ready=True, message="Model is installed and will be loaded on the first analysis (the first request is slower).")
        else:
            base.update(ready=True, message="Model is loaded and ready.")
        return base
    # gemini: reachability of a hosted API is not probed (no call, no cost); a key being present is the check.
    base.update(model=settings.gemini_model, runtime="hosted via Gemini API", reachable=bool(settings.gemini_api_key),
                model_installed=bool(settings.gemini_api_key), model_loaded=bool(settings.gemini_api_key),
                ready=bool(settings.gemini_api_key))
    base["message"] = "API key configured (the hosted model is contacted only during an analysis)." if settings.gemini_api_key else "GEMINI_API_KEY is not set."
    if not settings.gemini_api_key:
        base["setup_hint"] = "Add GEMINI_API_KEY to .env, or use the local provider: VISION_PROVIDER=ollama."
    return base


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        **_provider_health(),
        "timeout_seconds": settings.gemma_timeout_s,
        "max_upload_mb": settings.max_upload_mb,
        "allowed_types": sorted(ALLOWED_MIME),
        "catalog_version": load_catalog().version,
    }


@app.get("/api/templates")
def templates():
    return [
        {"id": t.id, "name": t.name, "summary": t.summary, "voltage_class": t.voltage_class, "supported_board_id": t.supported_board_id}
        for t in load_templates().values()
    ]


@app.get("/api/templates/{template_id}")
def template_detail(template_id: str):
    return cat_mod.template_payload(_tpl(template_id))


@app.get("/api/catalog")
def catalog_route():
    return cat_mod.catalog_payload()


def _require_demo_mode() -> None:
    if not settings.is_demo:
        raise HTTPException(404, "Synthetic test fixtures are only available when the server is started with VISION_PROVIDER=demo.")


@app.get("/api/fixtures")
def fixtures():
    if not settings.is_demo:
        return []
    return [{k: v for k, v in f.items() if not k.startswith("_") and k != "landmarks"} for f in list_fixtures().values()]


@app.get("/api/fixtures/{fixture_id}/image")
def fixture_image(fixture_id: str):
    _require_demo_mode()
    meta = list_fixtures().get(fixture_id)
    if not meta:
        raise HTTPException(404, "Unknown demo fixture.")
    return Response(Path(meta["_photo"]).read_bytes(), media_type="image/jpeg")


def _sample_catalog() -> dict[str, dict]:
    """Photos Wirewise can start a session from: real photos (if supplied) and the SYNTHETIC demo images."""
    out: dict[str, dict] = {}
    for sid, (filename, title, desc) in SAMPLE_PHOTOS.items():
        path = settings.samples_dir / filename
        if path.is_file():
            out[sid] = {"title": title, "description": desc, "path": path, "synthetic": False, "fixture_id": None}
    for fid, meta in list_fixtures().items():
        out[f"synthetic_{fid}"] = {
            "title": meta["title"], "description": meta["description"], "path": Path(meta["_photo"]),
            "synthetic": True, "fixture_id": fid,
        }
    return out


def _sample(sample_id: str) -> dict:
    entry = _sample_catalog().get(sample_id)
    if not entry:
        raise HTTPException(404, "Unknown sample photo.")
    return entry


@app.get("/api/samples")
def samples():
    """Sample images. Computer-generated ones are flagged `synthetic` and titled "Synthetic demo image"."""
    return [
        {"id": sid, "title": e["title"], "description": e["description"], "synthetic": e["synthetic"], "filename": e["path"].name}
        for sid, e in _sample_catalog().items()
    ]


@app.get("/api/samples/{sample_id}/image")
def sample_image(sample_id: str):
    return Response(_sample(sample_id)["path"].read_bytes(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


# --------------------------------------------------------------------------- sessions


@app.post("/api/sessions", response_model=ImageSession)
async def create_session(template_id: str = Form(...), file: UploadFile = File(...)):
    _tpl(template_id)
    if file.content_type and file.content_type.lower() not in ALLOWED_MIME:
        raise HTTPException(415, "Unsupported file type. Use a JPEG, PNG or WebP image.")
    limit = int(settings.max_upload_mb * 1024 * 1024)
    data = await file.read(limit + 1)
    try:
        img = validate_and_normalize(data, file.content_type, settings.max_upload_mb)
    except UploadError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _new_session(template_id, img.jpeg_bytes, img.width, img.height).session


@app.post("/api/sessions/sample", response_model=ImageSession)
def create_sample_session(body: dict):
    """Start a normal session from a sample image (same validation, same analysis path as an upload)."""
    template_id = body.get("template_id")
    _tpl(template_id or "")
    entry = _sample(str(body.get("sample_id") or ""))
    try:
        img = validate_and_normalize(entry["path"].read_bytes(), "image/jpeg", settings.max_upload_mb)
    except UploadError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _new_session(template_id, img.jpeg_bytes, img.width, img.height, fixture_id=entry["fixture_id"], synthetic=entry["synthetic"]).session


@app.post("/api/sessions/demo", response_model=ImageSession)
def create_demo_session(body: dict):
    _require_demo_mode()
    template_id, fixture_id = body.get("template_id"), body.get("fixture_id")
    _tpl(template_id or "")
    meta = list_fixtures().get(fixture_id or "")
    if not meta:
        raise HTTPException(404, "Unknown demo fixture.")
    jpeg = Path(meta["_photo"]).read_bytes()
    img = validate_and_normalize(jpeg, "image/jpeg", settings.max_upload_mb)
    return _new_session(template_id, img.jpeg_bytes, img.width, img.height, fixture_id=fixture_id, synthetic=True).session


@app.get("/api/sessions/{sid}", response_model=ImageSession)
def get_session(sid: str):
    return _state(sid).session


@app.delete("/api/sessions/{sid}", status_code=204)
def delete_session(sid: str):
    if not store.delete(sid):
        raise HTTPException(404, "Session not found.")
    return Response(status_code=204)


@app.get("/api/sessions/{sid}/image")
def session_image(sid: str):
    return Response(_state(sid).image_jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


# --------------------------------------------------------------------------- calibration


@app.post("/api/sessions/{sid}/calibrate", response_model=CalibrationResult)
def calibrate_session(sid: str, body: CalibrationRequest):
    state = _state(sid)
    tpl = _tpl(state.session.circuit_template_id)
    board = load_catalog().breadboards[tpl.breadboard_model_id]
    img = decode_bgr(state.image_jpeg)
    result = calibrate(body.points, img, board)
    if result.status != "failed":
        H = np.array(result.homography)
        rect = rectify(img, H, board, PX_PER_PITCH, MARGIN_PITCH)
        state.rectified_jpeg = encode_jpeg(rect)
        result.rectified = RectifiedInfo(width=rect.shape[1], height=rect.shape[0], px_per_pitch=PX_PER_PITCH, margin_pitch=MARGIN_PITCH)
    state.session.calibration_points = body.points
    state.session.calibration = result
    # A new calibration invalidates earlier proposals: their hole snapping used the old grid.
    state.observations = [o for o in state.observations if o.source == "user"]
    return result


@app.post("/api/sessions/{sid}/calibration/accept", response_model=CalibrationResult)
def accept_calibration(sid: str):
    state = _state(sid)
    cal = _calibrated(state)
    cal.accepted_by_user = True
    return cal


@app.get("/api/sessions/{sid}/rectified.jpg")
def rectified(sid: str):
    state = _state(sid)
    if not state.rectified_jpeg:
        raise HTTPException(409, "Calibrate the photo first.")
    return Response(state.rectified_jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


# --------------------------------------------------------------------------- observations


@app.post("/api/sessions/{sid}/analyze", response_model=AnalyzeResponse)
def analyze(sid: str, body: AnalyzeRequest):
    state = _state(sid)
    cal = _calibrated(state)
    if cal.status == "low_confidence" and not (cal.accepted_by_user or body.accept_unverified_calibration):
        raise HTTPException(
            409,
            "Calibration is low-confidence. Adjust the landmarks until the grid lines up, or explicitly accept it. " + " ".join(cal.messages),
        )
    tpl = _tpl(state.session.circuit_template_id)
    catalog = load_catalog()
    img = decode_bgr(state.image_jpeg)
    board = catalog.breadboards[tpl.breadboard_model_id]
    annotated = encode_jpeg(annotate_for_model(img, np.array(cal.homography), board), 90)
    ctx = ProposeContext(
        session_id=sid, template=tpl, catalog=catalog, image_jpeg=state.image_jpeg, annotated_jpeg=annotated,
        width=state.session.width, height=state.session.height, calibration=cal, fixture_id=state.session.fixture_id,
    )
    name = settings.vision_provider
    # Exactly the configured provider runs. A failure is reported to the user; it never switches provider.
    try:
        provider = get_provider(settings)
        raw = provider.propose(ctx)
    except ProviderError as exc:
        status = 503 if exc.code in ("unavailable", "timeout") else 502 if exc.retriable or exc.code == "bad_response" else 400
        raise HTTPException(status, exc.message) from exc

    proposals = normalize(raw, ctx, img, "demo" if name == "demo" else "gemma", provider.info)
    outline = _outline_observation(sid, state)
    # Replace earlier model proposals; keep anything the user added by hand.
    state.observations = [o for o in state.observations if o.source == "user" and o.observation_type != "board"] + [outline] + proposals
    state.session.last_provider = name
    warnings = []
    if not proposals:
        warnings.append("The provider did not report any items. Check the photo guidance, or add observations manually.")
    if name == "demo":
        warnings.append("DEMO MODE: no model is analyzing this image. These proposals are scripted synthetic fixtures.")
    return AnalyzeResponse(observations=state.observations, provider=provider.info, warnings=warnings)


def _outline_observation(sid: str, state: SessionState) -> Observation:
    pts = state.session.calibration_points or {}
    poly = [pts[k] for k in ("a1", "a30", "j30", "j1") if k in pts]
    return Observation(
        id="ob_breadboard", image_session_id=sid, observation_type="board",
        candidate_part_or_endpoint=Candidate(part_id=None, label="Calibrated breadboard outline"),
        bounding_box_or_polygon=poly, confidence_label="high", source="user", status="confirmed",
        evidence=[Evidence(source="user", note="Outline from the four landmarks you placed."), Evidence(source="opencv", note="Perspective and grid derived from those landmarks.")],
        display_name="Breadboard (calibrated)",
    )


@app.get("/api/sessions/{sid}/observations", response_model=list[Observation])
def list_observations(sid: str):
    return _state(sid).observations


@app.patch("/api/sessions/{sid}/observations/{oid}", response_model=Observation)
def update_observation(sid: str, oid: str, body: ObservationAction):
    state = _state(sid)
    obs = next((o for o in state.observations if o.id == oid), None)
    if not obs:
        raise HTTPException(404, "Observation not found.")
    if body.action == "confirm":
        obs.status = "confirmed" if obs.status != "corrected" else "corrected"
        obs.evidence.append(Evidence(source="user", note="Confirmed by you."))
    elif body.action == "reject":
        obs.status = "rejected"
        obs.evidence.append(Evidence(source="user", note="Rejected by you."))
    elif body.action == "reset":
        if obs.original_candidate is not None:
            obs.candidate_part_or_endpoint = obs.original_candidate
            obs.original_candidate = None
            if obs.original_source:
                obs.source = obs.original_source
                obs.original_source = None
            obs.display_name = _display_name(obs.candidate_part_or_endpoint, obs.display_name)
            obs.confidence_label = "uncertain"  # the original confidence is not restored; ask for a fresh review
        obs.status = "proposed"
    elif body.action == "correct":
        if body.candidate is None:
            raise HTTPException(422, "A correction needs a candidate.")
        new = _validate_candidate(body.candidate, state.session.circuit_template_id)
        if obs.original_candidate is None:
            obs.original_candidate = obs.candidate_part_or_endpoint
            obs.original_source = obs.source
        obs.candidate_part_or_endpoint = new
        obs.status = "corrected"
        obs.source = "user"
        obs.evidence.append(Evidence(source="user", note=body.note or "Corrected by you."))
        obs.confidence_label = "high"
        obs.display_name = _display_name(new, obs.display_name)
    obs.updated_at = utcnow()
    return obs


def _display_name(c: Candidate, fallback: str) -> str:
    if c.part_id == "jumper_wire":
        def d(e: Endpoint | None) -> str:
            return (e.hole or e.board_pin or e.kind) if e else "?"
        return f"Jumper wire {d(c.endpoints.get('end_a'))} → {d(c.endpoints.get('end_b'))}"
    return fallback


@app.post("/api/sessions/{sid}/observations", response_model=Observation, status_code=201)
def add_observation(sid: str, body: NewObservationRequest):
    state = _state(sid)
    cand = _validate_candidate(body.candidate, state.session.circuit_template_id)
    if cand.part_id is None:
        raise HTTPException(422, "Choose a catalog part for a manual observation.")
    obs = Observation(
        id="ob_" + uuid.uuid4().hex[:8], image_session_id=sid, observation_type=body.observation_type,
        candidate_part_or_endpoint=cand, bounding_box_or_polygon=[], confidence_label="high", source="user",
        status="corrected", evidence=[Evidence(source="user", note=body.note or "Added by you.")],
        display_name=_display_name(cand, load_catalog().parts[cand.part_id].display_name),
    )
    state.observations.append(obs)
    return obs


@app.delete("/api/sessions/{sid}/observations/{oid}", status_code=204)
def delete_observation(sid: str, oid: str):
    state = _state(sid)
    obs = next((o for o in state.observations if o.id == oid), None)
    if not obs or obs.source != "user":
        raise HTTPException(404, "Only observations you added can be deleted. Reject model proposals instead.")
    state.observations.remove(obs)
    return Response(status_code=204)


# --------------------------------------------------------------------------- report


def _report(state: SessionState) -> Report:
    tpl = _tpl(state.session.circuit_template_id)
    return compare(state.session.id, tpl, load_catalog(), state.observations, state.session.calibration)


@app.get("/api/sessions/{sid}/report", response_model=Report)
def report(sid: str):
    return _report(_state(sid))


# --------------------------------------------------------------------------- explicit save


@app.post("/api/sessions/{sid}/save")
def save_project(sid: str, body: dict):
    state = _state(sid)
    name = str(body.get("name") or "Untitled Wirewise project")[:80]
    return db.save_project(name, state, _report(state))


@app.get("/api/projects")
def projects():
    return db.list_projects()


@app.delete("/api/projects/{pid}", status_code=204)
def delete_project(pid: str):
    if not db.delete_project(pid):
        raise HTTPException(404, "Project not found.")
    return Response(status_code=204)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    # Never leak internals or secrets in an error body.
    return JSONResponse(status_code=500, content={"detail": "Unexpected server error."})
