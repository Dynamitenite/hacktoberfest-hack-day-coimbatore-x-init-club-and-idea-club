import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type {
  Calibration, Candidate, Health, Observation, Point, ProviderInfo, Report, Sample, Session, TemplateDetail, TemplateSummary,
} from "@/lib/types";
import FindingsPanel from "./FindingsPanel";
import ModelStatus from "./ModelStatus";
import ObservationEditor from "./ObservationEditor";
import ObservationList from "./ObservationList";
import PhotoCanvas, { LANDMARK_ORDER } from "./PhotoCanvas";
import Schematic from "./Schematic";
import { Spinner } from "./ui";

type Step = 1 | 2 | 3;
type Busy = null | "upload" | "calibrate" | "analyze" | "report" | "save";

const GUIDANCE = [
  "Show the whole breadboard and the Arduino header pins you use.",
  "Shoot from straight above, with the board filling most of the frame.",
  "Use bright, even light. Avoid glare on the plastic and shadows over the holes.",
  "Keep hands, cables and labels out of the way of wires and part leads.",
];

function defaultLandmarks(w: number, h: number): Record<string, Point> {
  return {
    a1: { x: w * 0.2, y: h * 0.32 },
    a30: { x: w * 0.8, y: h * 0.32 },
    j30: { x: w * 0.8, y: h * 0.7 },
    j1: { x: w * 0.2, y: h * 0.7 },
  };
}

export default function WirewiseApp() {
  const [health, setHealth] = useState<Health | null>(null);
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [samples, setSamples] = useState<Sample[]>([]); // bundled sample images: synthetic demo images, plus real photos if supplied
  const [checkingHealth, setCheckingHealth] = useState(false);
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [detail, setDetail] = useState<TemplateDetail | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);

  const [step, setStep] = useState<Step>(1);
  const [session, setSession] = useState<Session | null>(null);
  const [landmarks, setLandmarks] = useState<Record<string, Point>>({});
  const [cal, setCal] = useState<Calibration | null>(null);
  const [calNonce, setCalNonce] = useState(0);
  const [analyzed, setAnalyzed] = useState(false);
  const [obs, setObs] = useState<Observation[]>([]);
  const [provider, setProvider] = useState<ProviderInfo | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [report, setReport] = useState<Report | null>(null);

  const [busy, setBusy] = useState<Busy>(null);
  const [busyObs, setBusyObs] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedObs, setSelectedObs] = useState<string | null>(null);
  const [focusFinding, setFocusFinding] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ obs: Observation | null } | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const photoRef = useRef<HTMLDivElement>(null);
  const schematicRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);

  /* ---------------- boot ---------------- */
  useEffect(() => {
    (async () => {
      try {
        const [h, t, sm] = await Promise.all([api.health(), api.templates(), api.samples()]);
        setHealth(h);
        setTemplates(t);
        setSamples(sm);
        if (t[0]) setTemplateId(t[0].id);
      } catch (e) {
        setBootError(e instanceof ApiError ? e.message : "Could not start Wirewise.");
      }
    })();
  }, []);

  useEffect(() => {
    if (!templateId) return;
    api.template(templateId).then(setDetail).catch((e) => setBootError(e.message));
  }, [templateId]);

  const recheckHealth = useCallback(async () => {
    setCheckingHealth(true);
    try {
      setHealth(await api.health());
    } catch {
      /* the backend itself is unreachable; the next API call reports it */
    } finally {
      setCheckingHealth(false);
    }
  }, []);

  // Keep the header status honest while the page is open (Ollama can be started or stopped at any time).
  useEffect(() => {
    const t = window.setInterval(() => {
      if (!document.hidden) recheckHealth();
    }, 20000);
    return () => window.clearInterval(t);
  }, [recheckHealth]);

  const run = useCallback(async <T,>(label: Busy, fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(label);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
      return undefined;
    } finally {
      setBusy(null);
    }
  }, []);

  /* ---------------- step 1: choose + start ---------------- */
  const beginSession = (s: Session, note: string) => {
    setSession(s);
    setLandmarks(s.suggested_landmarks && LANDMARK_ORDER.every((k) => s.suggested_landmarks?.[k]) ? s.suggested_landmarks : defaultLandmarks(s.width, s.height));
    setCal(null);
    setAnalyzed(false);
    setObs([]);
    setReport(null);
    setProvider(null);
    setWarnings([]);
    setSelectedObs(null);
    setFocusFinding(null);
    setNotice(note);
    setStep(2);
    window.scrollTo({ top: 0 });
  };

  const startFromFile = async (file: File | undefined | null) => {
    if (!file || !templateId || !health) return;
    if (!health.allowed_types.includes(file.type)) return setError("Use a JPEG, PNG or WebP photo.");
    if (file.size > health.max_upload_mb * 1024 * 1024) return setError(`That photo is larger than ${health.max_upload_mb} MB. Choose a smaller one.`);
    const s = await run("upload", () => api.upload(templateId, file));
    if (s) beginSession(s, s.suggested_landmarks ? "Corners were placed automatically from the photo. Check each one." : "Drag the four handles onto the corner holes.");
  };

  const startFromSample = async (sm: Sample) => {
    if (!templateId) return;
    const s = await run("upload", () => api.sampleSession(templateId, sm.id));
    if (s) beginSession(s, s.synthetic ? "Synthetic demo image loaded (computer-generated, not a real photo). The corner handles are pre-placed; check them like you would on your own photo." : "Sample photo loaded. Drag the four handles onto the corner holes, then check the grid.");
  };

  const startOver = async () => {
    if (session) api.deleteSession(session.id).catch(() => undefined);
    setSession(null);
    setStep(1);
    setReport(null);
    setObs([]);
    setCal(null);
    setAnalyzed(false);
    setError(null);
    setNotice(null);
  };

  /* ---------------- step 2: calibrate + analyze ---------------- */
  const checkGrid = async () => {
    if (!session) return;
    const c = await run("calibrate", () => api.calibrate(session.id, landmarks));
    if (c) {
      setCal(c);
      setCalNonce((n) => n + 1);
      if (analyzed) {
        setAnalyzed(false);
        setObs((o) => o.filter((x) => x.source === "user"));
        setReport(null);
      }
    }
  };

  const analyze = async (acceptLow = false) => {
    if (!session) return;
    const r = await run("analyze", async () => {
      if (acceptLow) setCal(await api.acceptCalibration(session.id));
      return api.analyze(session.id, acceptLow);
    });
    if (!r) recheckHealth(); // the failure may be "model unavailable": refresh the header status and setup panel
    if (r) {
      setObs(r.observations);
      setProvider(r.provider);
      setWarnings(r.warnings);
      setAnalyzed(true);
      setNotice(null);
    }
  };

  /* ---------------- step 2: review ---------------- */
  const act = async (oid: string, action: "confirm" | "reject" | "reset") => {
    if (!session) return;
    setBusyObs(oid);
    const updated = await run(null, () => api.act(session.id, oid, action));
    setBusyObs(null);
    if (updated) {
      setObs((list) => list.map((o) => (o.id === oid ? updated : o)));
      if (step === 3) refreshReport();
    }
  };

  const refreshReport = useCallback(async () => {
    if (!session) return;
    try {
      setReport(await api.report(session.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not refresh the report.");
    }
  }, [session]);

  const submitEditor = async (candidate: Candidate, type: "component" | "wire"): Promise<string | null> => {
    if (!session || !editing) return "No active session.";
    try {
      if (editing.obs) {
        const updated = await api.correct(session.id, editing.obs.id, candidate);
        setObs((list) => list.map((o) => (o.id === updated.id ? updated : o)));
      } else {
        const created = await api.addObservation(session.id, type, candidate);
        setObs((list) => [...list, created]);
      }
      setEditing(null);
      if (step === 3) await refreshReport();
      return null;
    } catch (e) {
      return e instanceof Error ? e.message : "Could not save.";
    }
  };

  const removeObs = async (o: Observation) => {
    if (!session) return;
    setBusyObs(o.id);
    const ok = await run(null, async () => (await api.deleteObservation(session.id, o.id), true));
    setBusyObs(null);
    if (ok) setObs((list) => list.filter((x) => x.id !== o.id));
  };

  const check = async () => {
    if (!session) return;
    const r = await run("report", () => api.report(session.id));
    if (r) {
      setReport(r);
      setFocusFinding(null);
      setStep(3);
      window.scrollTo({ top: 0 });
    }
  };

  const save = async () => {
    if (!session || !detail) return;
    const r = await run("save", () => api.save(session.id, `${detail.template.name} · ${new Date().toLocaleString()}`));
    if (r) setNotice(`Saved as “${r.name}”. The photo is now stored on this server until you delete the project.`);
  };

  /* ---------------- derived ---------------- */
  const focusedFinding = report?.findings.find((f) => f.id === focusFinding) ?? null;
  const editableObs = useMemo(
    () => new Set(obs.filter((o) => (o.observation_type === "component" || o.observation_type === "wire") && o.candidate_part_or_endpoint.part_id).map((o) => o.id)),
    [obs],
  );
  const demoActive = !!health?.demo_mode;
  const rectifiedSrc = session && cal && cal.status !== "failed" ? api.rectifiedUrl(session.id, calNonce) : undefined;
  const reviewRemaining = obs.filter((o) => (o.observation_type === "component" || o.observation_type === "wire") && o.status === "proposed").length;

  const focusOn = (id: string, target: "photo" | "schematic") => {
    setFocusFinding(id);
    (target === "photo" ? photoRef : schematicRef).current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
  };

  /* ---------------- render ---------------- */
  if (bootError) {
    return (
      <main className="page">
        <div className="alert" role="alert">
          <div>
            <p>Wirewise could not start.</p>
            <p className="small" style={{ fontWeight: 400 }}>{bootError}</p>
            <p className="small" style={{ fontWeight: 400 }}>Start the backend (<code>uvicorn app.main:app</code> in <code>backend/</code>), then reload this page.</p>
          </div>
        </div>
      </main>
    );
  }
  if (!health || !detail || !templateId) {
    return (
      <main className="page">
        <div className="skeleton" role="status"><Spinner label="Loading the circuit catalog…" /></div>
      </main>
    );
  }

  const template = detail.template;
  const columnOffsets = detail.breadboard.column_offsets_pitch;

  return (
    <>
      {demoActive && (
        <div className="demo-band" role="status">
          DEMO MODE: no model is analyzing this image. Observations are scripted demo data for the bundled synthetic demo images only.
        </div>
      )}
      <header className="topbar">
        <div className="brand">
          <svg width="34" height="34" viewBox="0 0 34 34" aria-hidden>
            <rect x="1" y="1" width="32" height="32" rx="7" fill="#15262b" />
            <circle cx="9" cy="24" r="3.4" fill="#fff" />
            <circle cx="25" cy="10" r="3.4" fill="#fff" />
            <path d="M9 24 H17 L17 10 H25" fill="none" stroke="#5be3a6" strokeWidth="3" strokeLinejoin="round" />
          </svg>
          Wirewise
        </div>
        <nav className="trace" aria-label="Progress">
          {[
            { n: 1 as Step, label: "Choose circuit", enabled: true },
            { n: 2 as Step, label: "Inspect photo", enabled: !!session },
            { n: 3 as Step, label: "Review findings", enabled: !!report },
          ].map((s, i) => (
            <div key={s.n} style={{ display: "contents" }}>
              {i > 0 && <span className="trace-line" aria-hidden data-done={step >= s.n} />}
              <button
                type="button"
                className="trace-step"
                disabled={!s.enabled}
                aria-current={step === s.n ? "step" : undefined}
                data-state={step === s.n ? "current" : step > s.n ? "done" : "todo"}
                onClick={() => setStep(s.n)}
              >
                <span className="plug" aria-hidden>{step > s.n ? "✓" : s.n}</span>
                <span className="trace-label">{s.label}</span>
              </button>
            </div>
          ))}
        </nav>
        <div className="spacer" />
        <ModelStatus health={health} checking={checkingHealth} onRecheck={recheckHealth} />
      </header>

      <main className="page">
        {error && (
          <div className="alert" role="alert">
            <span>{error}</span>
            <button type="button" className="btn btn-small btn-quiet" onClick={() => setError(null)}>Dismiss</button>
          </div>
        )}
        {notice && step !== 1 && (
          <p className="small" role="status" style={{ marginBottom: "0.8rem", fontWeight: 600 }}>{notice}</p>
        )}

        {/* ======================= STEP 1 ======================= */}
        {step === 1 && (
          <div className="choose">
            <div className="stack">
              <div>
                <h1>Does your breadboard match the circuit you meant to build?</h1>
                <p className="muted" style={{ marginTop: 8, maxWidth: "62ch" }}>
                  Pick a supported circuit, photograph your build, and confirm what Gemma 4 spots. Wirewise then compares your confirmed connections with the template and shows where they differ.
                </p>
              </div>

              <section className="panel" aria-labelledby="tpl-h">
                <div className="panel-head">
                  <h2 id="tpl-h">{template.name}</h2>
                  <span className="badge" data-tone="plain">Low voltage · USB-powered board</span>
                </div>
                <p>{template.summary}</p>
                <div className="stack" style={{ marginTop: 12 }}>
                  <Schematic diagram={template.reference_diagram} title={template.name} />
                  <div>
                    <h3>Connections the template requires</h3>
                    <ul className="checklist" style={{ marginTop: 8 }}>
                      {template.explicit_rules.map((r) => (
                        <li key={r.id}><span className="tick" aria-hidden>✓</span><span>{r.text}</span></li>
                      ))}
                    </ul>
                  </div>
                </div>
              </section>

              <section className="panel" aria-labelledby="hw-h">
                <div className="panel-head"><h2 id="hw-h">Supported hardware</h2><span className="small muted">Catalog facts are copied from the sources listed, never guessed from a photo.</span></div>
                <div className="parts">
                  {Object.values(detail.parts).map((p) => (
                    <div className="part" key={p.id}>
                      <strong>{p.display_name}</strong>
                      <p className="small muted">Terminals: {p.terminals.map((t) => t.name).join(", ")}</p>
                      <p className="small muted">{p.electrical_limits_note}</p>
                      {p.sources[0]?.url ? <p className="small"><a href={p.sources[0].url} target="_blank" rel="noreferrer">Source: {p.sources[0].title}</a></p> : null}
                    </div>
                  ))}
                  <div className="part">
                    <strong>{detail.breadboard.display_name}</strong>
                    <p className="small muted">Rows {1}–{detail.breadboard.rows}, columns {detail.breadboard.columns[0]}–{detail.breadboard.columns[detail.breadboard.columns.length - 1]}. Rows join within a–e and within f–j; the centre channel separates them.</p>
                    <p className="small muted">{detail.breadboard.unsupported_regions[0]?.description}</p>
                  </div>
                </div>
              </section>

              <section className="empty" aria-label="Unsupported circuits" style={{ textAlign: "left" }}>
                <strong>Building something else?</strong>
                <p className="small">This version checks only the circuit above. Other boards, arbitrary schematics, mains wiring, high-energy batteries and motor circuits are not supported, and Wirewise will say so rather than guess.</p>
              </section>
            </div>

            <div className="stack sticky">
              <section className="panel" aria-labelledby="start-h">
                <h2 id="start-h">Add a photo of your build</h2>
                <ul className="checklist" style={{ margin: "10px 0" }}>
                  {GUIDANCE.map((g) => (<li key={g}><span className="tick" aria-hidden>✓</span><span>{g}</span></li>))}
                </ul>
                <div
                  className="dropzone"
                  data-over={dragOver}
                  onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={(e) => { e.preventDefault(); setDragOver(false); startFromFile(e.dataTransfer.files?.[0]); }}
                >
                  <p><strong>Drop a photo here</strong> <span className="muted">or</span></p>
                  <div className="btn-row" style={{ justifyContent: "center" }}>
                    <button type="button" className="btn btn-primary" onClick={() => fileRef.current?.click()} disabled={busy === "upload"}>
                      {busy === "upload" ? <Spinner label="Uploading…" /> : "Choose a photo"}
                    </button>
                    <button type="button" className="btn" onClick={() => cameraRef.current?.click()} disabled={busy === "upload"}>Take a photo</button>
                  </div>
                  <p className="small muted">JPEG, PNG or WebP, up to {health.max_upload_mb} MB. The photo stays in memory for this session unless you save the project.</p>
                  <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" aria-label="Choose a photo" onChange={(e) => { startFromFile(e.target.files?.[0]); e.target.value = ""; }} />
                  <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="sr-only" aria-label="Take a photo with the camera" onChange={(e) => { startFromFile(e.target.files?.[0]); e.target.value = ""; }} />
                </div>
              </section>

              {samples.length > 0 && (
                <section className="panel" aria-labelledby="sample-h">
                  <h2 id="sample-h">Or try a sample image</h2>
                  <p className="small muted" style={{ margin: "6px 0 10px" }}>
                    Images marked <strong>Synthetic demo image</strong> are computer-generated, not real photos. Every sample goes through the same calibration and analysis as a photo you upload.
                  </p>
                  <div className="stack" style={{ gap: 10 }}>
                    {samples.map((sm) => (
                      <button key={sm.id} type="button" className="fixture" disabled={busy === "upload"} onClick={() => startFromSample(sm)}>
                        <img src={api.sampleImageUrl(sm.id)} alt="" />
                        <span>
                          {sm.synthetic ? <span className="badge" data-tone="warn" style={{ marginBottom: 4 }}>Synthetic demo image</span> : null}
                          <strong style={{ display: "block" }}>{sm.title}</strong>
                          <span className="small muted" style={{ display: "block" }}>{sm.description}</span>
                        </span>
                      </button>
                    ))}
                  </div>
                </section>
              )}
            </div>
          </div>
        )}

        {/* ======================= STEP 2 ======================= */}
        {step === 2 && session && (
          <div className="split">
            <div className="stack">
              <section className="panel" aria-labelledby="photo-h" ref={photoRef}>
                <div className="panel-head">
                  <h2 id="photo-h">{analyzed ? "Review what Gemma proposed" : "Mark the breadboard corners"}</h2>
                  {session.synthetic ? <span className="badge" data-tone="warn">Synthetic demo image</span> : null}
                  {analyzed && provider ? (
                    <span className="badge" data-tone={provider.is_demo ? "warn" : "plain"}>
                      {provider.is_demo ? "DEMO DATA: no model ran" : `Proposed by Gemma 4 · ${provider.model} · ${provider.runtime}`}
                    </span>
                  ) : null}
                </div>
                {!analyzed && (
                  <p className="small muted" style={{ marginBottom: 10 }}>
                    Drag each handle onto the matching corner hole: <span className="hole">a1</span>, <span className="hole">a30</span>, <span className="hole">j30</span>, <span className="hole">j1</span>. Row numbers run along the long side of the board, column letters across it. <span className="kbd-hint">Arrow keys nudge a handle by 1 px, Shift by 10.</span>
                  </p>
                )}
                <PhotoCanvas
                  mode={analyzed ? "observe" : "calibrate"}
                  src={api.imageUrl(session.id)}
                  width={session.width}
                  height={session.height}
                  landmarks={landmarks}
                  onLandmarksChange={analyzed ? undefined : (l) => { setLandmarks(l); if (cal) setCal({ ...cal, status: cal.status, messages: ["Corners moved. Check the grid again."] }); }}
                  calibration={cal}
                  rectifiedSrc={rectifiedSrc}
                  columnOffsets={columnOffsets}
                  observations={obs}
                  selectedObsId={selectedObs}
                  onSelectObs={(id) => {
                    setSelectedObs(id);
                    if (id) document.getElementById(`obs-${id}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
                  }}
                />
                {analyzed && (
                  <div className="legend" aria-label="Marker legend">
                    <span className="legend-item"><span className="swatch" data-s="proposed" /> Proposed (dashed, needs review)</span>
                    <span className="legend-item"><span className="swatch" data-s="confirmed" /> Confirmed (solid ✓)</span>
                    <span className="legend-item"><span className="swatch" data-s="rejected" /> Rejected (dotted ✕)</span>
                    <span className="legend-item">? marks low or uncertain confidence</span>
                  </div>
                )}
              </section>
            </div>

            <div className="stack sticky">
              {!analyzed ? (
                <section className="panel" aria-labelledby="cal-h">
                  <h2 id="cal-h">Check the grid</h2>
                  <p className="small muted" style={{ margin: "6px 0 10px" }}>
                    Wirewise maps your four corners to the breadboard's hole grid. The cyan dots must land on real holes before it looks for parts.
                  </p>
                  <div className="btn-row">
                    <button type="button" className="btn btn-primary" onClick={checkGrid} disabled={busy === "calibrate"}>
                      {busy === "calibrate" ? <Spinner label="Checking…" /> : cal ? "Check the grid again" : "Check the grid"}
                    </button>
                  </div>
                  {cal && (
                    <div role="status" aria-live="polite" style={{ marginTop: 12 }}>
                      <span className="badge" data-tone={cal.status === "ok" ? "ok" : cal.status === "failed" ? "bad" : "review"}>
                        {cal.status === "ok" ? "✓ Grid lines up" : cal.status === "failed" ? "✕ Cannot build a grid" : "? Grid is uncertain"}
                      </span>
                      <ul style={{ marginTop: 8, display: "grid", gap: 4 }}>{cal.messages.map((m) => <li key={m} className="small">{m}</li>)}</ul>
                      {cal.metrics && (
                        <dl className="kv" style={{ marginTop: 8 }}>
                          <dt>Holes matched</dt><dd>{Math.round(cal.metrics.holes_visible_fraction * 100)}% of {cal.metrics.holes_checked}</dd>
                          <dt>Hole spacing</dt><dd>{cal.metrics.pitch_px_min.toFixed(1)} px</dd>
                        </dl>
                      )}
                    </div>
                  )}

                  {cal && cal.status !== "failed" && (
                    <div style={{ marginTop: 14, display: "grid", gap: 10 }}>
                      {!health.ready && !health.demo_mode ? (
                        <div className="unavailable" role="alert">
                          <strong>Gemma 4 is unavailable, so Wirewise cannot analyze this photo.</strong>
                          <p className="small">{health.message}</p>
                          {health.setup_hint && <pre>{health.setup_hint}</pre>}
                          <p className="small">Wirewise never switches to demo data on its own. After fixing this, check again.</p>
                          <div className="btn-row">
                            <button type="button" className="btn btn-small" onClick={recheckHealth} disabled={checkingHealth}>{checkingHealth ? "Checking…" : "Check again"}</button>
                          </div>
                        </div>
                      ) : (
                        <p className="small muted">
                          {health.demo_mode
                            ? "Demo mode: scripted proposals, no model."
                            : <>Gemma 4 (<span className="mono">{health.model}</span>, {health.runtime}) will look at this one photo. On a CPU this can take up to {health.timeout_seconds} s{health.model_loaded ? "" : "; the first run also loads the model"}.</>}
                        </p>
                      )}
                      <div className="btn-row">
                        <button type="button" className="btn btn-primary" disabled={busy === "analyze" || (cal.status === "low_confidence") || !health.ready} onClick={() => analyze(false)}>
                          {busy === "analyze" ? <Spinner label={health.demo_mode ? "Loading demo proposals…" : "Asking Gemma 4…"} /> : "Find parts and wires"}
                        </button>
                        {cal.status === "low_confidence" && (
                          <button type="button" className="btn btn-quiet" disabled={busy === "analyze" || !health.ready} onClick={() => analyze(true)}>
                            Use this grid anyway
                          </button>
                        )}
                      </div>
                      {cal.status === "low_confidence" && (
                        <p className="small muted">If you continue anyway, the report can never say MATCHES TEMPLATE. It will stay at NEEDS REVIEW because hole positions are unverified.</p>
                      )}
                    </div>
                  )}
                </section>
              ) : (
                <section className="panel" aria-labelledby="rev-h">
                  <div className="panel-head">
                    <h2 id="rev-h">Confirm what is really there</h2>
                  </div>
                  {warnings.map((w) => <p key={w} className="small" style={{ marginBottom: 6, fontWeight: 600, color: "var(--warn)" }}>{w}</p>)}
                  <p className="small muted" style={{ marginBottom: 12 }}>
                    {provider?.is_demo ? "DEMO DATA: these proposals are scripted for a synthetic demo image; no model analyzed anything. " : `Gemma 4 (${provider?.model}, ${provider?.runtime}) looked at the photo and proposed these. `}
                    Nothing becomes part of the circuit until you confirm it. Wirewise, not the model, decides what differs from the template.
                  </p>
                  <div className="btn-row" style={{ marginBottom: 14 }}>
                    <button type="button" className="btn btn-primary" onClick={check} disabled={busy === "report"}>
                      {busy === "report" ? <Spinner label="Comparing…" /> : "Check against the template"}
                    </button>
                    <button type="button" className="btn btn-quiet" onClick={() => { setAnalyzed(false); setSelectedObs(null); }}>Adjust corners</button>
                  </div>
                  {reviewRemaining > 0 && <p className="small" role="status" style={{ marginBottom: 12 }}>{reviewRemaining} proposal{reviewRemaining === 1 ? "" : "s"} still need your review. You can check now; unreviewed items will show as NEEDS REVIEW.</p>}
                  <ObservationList
                    observations={obs}
                    selectedId={selectedObs}
                    busyId={busyObs}
                    onSelect={(id) => setSelectedObs(id)}
                    onAct={act}
                    onEdit={(o) => setEditing({ obs: o })}
                    onRemove={removeObs}
                    onAdd={() => setEditing({ obs: null })}
                  />
                </section>
              )}

              <section className="panel" aria-labelledby="ref-h" ref={schematicRef}>
                <h2 id="ref-h" style={{ marginBottom: 8 }}>Intended circuit</h2>
                <Schematic diagram={template.reference_diagram} />
              </section>
            </div>
          </div>
        )}

        {/* ======================= STEP 3 ======================= */}
        {step === 3 && session && report && (
          <div className="split">
            <div className="stack">
              <section className="panel" aria-labelledby="ev-h" ref={photoRef}>
                <div className="panel-head">
                  <h2 id="ev-h">{session.synthetic ? "Evidence on the synthetic demo image" : "Evidence on your photo"}</h2>
                  {session.synthetic ? <span className="badge" data-tone="warn">Synthetic demo image</span> : null}
                  <div className="btn-row">
                    <button className="btn btn-small" type="button" onClick={() => setStep(2)}>Edit observations</button>
                    <button className="btn btn-small btn-quiet" type="button" onClick={refreshReport}>Re-run check</button>
                  </div>
                </div>
                <PhotoCanvas
                  mode="findings"
                  src={api.imageUrl(session.id)}
                  width={session.width}
                  height={session.height}
                  landmarks={landmarks}
                  calibration={cal}
                  findings={report.findings}
                  focusFindingId={focusFinding}
                  onFocusFinding={setFocusFinding}
                />
                <div className="legend">
                  <span className="legend-item"><span className="swatch" data-s="mismatch" /> Possible mismatch</span>
                  <span className="legend-item"><span className="swatch" data-s="proposed" style={{ borderColor: "var(--review-line)", background: "rgba(138,88,196,0.16)" }} /> Needs review</span>
                  <span className="legend-item">Select a finding to highlight it here and on the schematic.</span>
                </div>
                {focusedFinding && focusedFinding.image_region.length < 3 && (
                  <p className="small muted" style={{ marginTop: 8 }}>This finding has no single place on the photo (for example, a part was never confirmed).</p>
                )}
              </section>
              <div className="btn-row">
                <button className="btn" type="button" onClick={save} disabled={busy === "save"}>{busy === "save" ? <Spinner label="Saving…" /> : "Save project"}</button>
                <button className="btn btn-quiet" type="button" onClick={startOver}>Start over with another photo</button>
              </div>
              {notice && <p className="small" role="status">{notice}</p>}
            </div>

            <div className="stack">
              <section className="panel" aria-labelledby="ref2-h" ref={schematicRef}>
                <h2 id="ref2-h" style={{ marginBottom: 8 }}>Expected connections</h2>
                <Schematic diagram={template.reference_diagram} edgeChecks={report.edge_checks} focusEdgeIds={focusedFinding?.expected_edge_ids ?? []} />
                <p className="hint" style={{ marginTop: 6 }}>Green: matched · red dashed: possible mismatch · violet dotted: needs review · black: not yet judged.</p>
              </section>
              <FindingsPanel report={report} detail={detail} focusId={focusFinding} onFocus={focusOn} onCorrect={(id) => setEditing({ obs: obs.find((o) => o.id === id) ?? null })} editableObs={editableObs} />
            </div>
          </div>
        )}

        <p className="footnote">
          Wirewise is an inspection and learning aid. It never powers, controls or talks to your hardware, and it does not say a circuit is safe to power. Gemma 4 proposes what is visible; the comparison itself is deterministic graph logic that uses only the template and the verified catalog.
        </p>
      </main>

      {editing && <ObservationEditor key={editing.obs?.id ?? "new"} detail={detail} observation={editing.obs} onClose={() => setEditing(null)} onSubmit={submitEditor} />}
    </>
  );
}
