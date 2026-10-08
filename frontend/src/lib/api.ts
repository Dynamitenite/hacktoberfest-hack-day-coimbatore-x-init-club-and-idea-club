import type {
  AnalyzeResponse, Calibration, Candidate, Health, Observation, Point, Report, Sample, Session, TemplateDetail, TemplateSummary,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

// Same-origin: the Vite dev server proxies /api to the FastAPI backend (see vite.config.ts).
async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError("Cannot reach the Wirewise backend. Start it with `uvicorn app.main:app` in backend/ and try again.", 0);
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status}).`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join(" ");
    } catch {
      if (res.status === 502 || res.status === 504 || res.status === 500) detail = "The backend is not responding. Check that it is running.";
    }
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  health: () => call<Health>("/api/health"),
  templates: () => call<TemplateSummary[]>("/api/templates"),
  template: (id: string) => call<TemplateDetail>(`/api/templates/${id}`),
  upload: (templateId: string, file: File) => {
    const fd = new FormData();
    fd.append("template_id", templateId);
    fd.append("file", file);
    return call<Session>("/api/sessions", { method: "POST", body: fd });
  },
  samples: () => call<Sample[]>("/api/samples"),
  sampleImageUrl: (id: string) => `/api/samples/${id}/image`,
  sampleSession: (templateId: string, sampleId: string) =>
    call<Session>("/api/sessions/sample", json("POST", { template_id: templateId, sample_id: sampleId })),
  deleteSession: (sid: string) => call<void>(`/api/sessions/${sid}`, { method: "DELETE" }),
  imageUrl: (sid: string) => `/api/sessions/${sid}/image`,
  rectifiedUrl: (sid: string, nonce: number) => `/api/sessions/${sid}/rectified.jpg?n=${nonce}`,
  calibrate: (sid: string, points: Record<string, Point>) => call<Calibration>(`/api/sessions/${sid}/calibrate`, json("POST", { points })),
  acceptCalibration: (sid: string) => call<Calibration>(`/api/sessions/${sid}/calibration/accept`, json("POST")),
  // The server decides which provider runs (VISION_PROVIDER); the browser cannot pick or substitute one.
  analyze: (sid: string, acceptUnverified = false) =>
    call<AnalyzeResponse>(`/api/sessions/${sid}/analyze`, json("POST", { accept_unverified_calibration: acceptUnverified })),
  act: (sid: string, oid: string, action: "confirm" | "reject" | "reset", note?: string) =>
    call<Observation>(`/api/sessions/${sid}/observations/${oid}`, json("PATCH", { action, note })),
  correct: (sid: string, oid: string, candidate: Candidate, note?: string) =>
    call<Observation>(`/api/sessions/${sid}/observations/${oid}`, json("PATCH", { action: "correct", candidate, note })),
  addObservation: (sid: string, observation_type: "component" | "wire", candidate: Candidate) =>
    call<Observation>(`/api/sessions/${sid}/observations`, json("POST", { observation_type, candidate })),
  deleteObservation: (sid: string, oid: string) => call<void>(`/api/sessions/${sid}/observations/${oid}`, { method: "DELETE" }),
  report: (sid: string) => call<Report>(`/api/sessions/${sid}/report`),
  save: (sid: string, name: string) => call<{ id: string; name: string }>(`/api/sessions/${sid}/save`, json("POST", { name })),
};
