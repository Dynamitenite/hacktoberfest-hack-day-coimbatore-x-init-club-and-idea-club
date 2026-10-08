"use client";

import { useMemo, useRef, useState } from "react";
import type { Calibration, Finding, Observation, Point, ResultState } from "@/lib/types";

export type CanvasMode = "calibrate" | "observe" | "findings";
export const LANDMARK_ORDER = ["a1", "a30", "j30", "j1"] as const;
const LANDMARK_HELP: Record<string, string> = {
  a1: "row 1, column a",
  a30: "row 30, column a",
  j30: "row 30, column j",
  j1: "row 1, column j",
};

type Props = {
  mode: CanvasMode;
  src: string;
  width: number;
  height: number;
  landmarks: Record<string, Point>;
  onLandmarksChange?: (next: Record<string, Point>) => void;
  calibration?: Calibration | null;
  rectifiedSrc?: string;
  columnOffsets?: Record<string, number>;
  observations?: Observation[];
  selectedObsId?: string | null;
  onSelectObs?: (id: string | null) => void;
  findings?: Finding[];
  focusFindingId?: string | null;
  onFocusFinding?: (id: string | null) => void;
};

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

const FINDING_COLOR: Record<ResultState, string> = {
  "POSSIBLE MISMATCH": "var(--bad-line)",
  "NEEDS REVIEW": "var(--review-line)",
  "NOT CHECKED": "var(--skip-line)",
  "MATCHES TEMPLATE": "var(--ok-line)",
};

function statusStyle(o: Observation) {
  const uncertain = o.confidence_label === "low" || o.confidence_label === "uncertain";
  switch (o.status) {
    case "confirmed":
    case "corrected":
      return { stroke: "var(--ok-line)", fill: "rgba(31,154,98,0.16)", dash: undefined, glyph: o.status === "corrected" ? "✎" : "✓", op: 1 };
    case "rejected":
      return { stroke: "var(--skip-line)", fill: "none", dash: "2 6", glyph: "✕", op: 0.7 };
    default:
      return { stroke: "var(--warn-line)", fill: "rgba(224,164,26,0.16)", dash: "9 6", glyph: uncertain ? "?" : "◌", op: 1 };
  }
}

function shortTag(o: Observation): string {
  const c = o.candidate_part_or_endpoint;
  if (c.template_ref) return c.template_ref;
  if (c.part_id === "jumper_wire") return "wire";
  return (c.kind_hint ?? "part").slice(0, 10);
}

export default function PhotoCanvas(p: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [drag, setDrag] = useState<string | null>(null);
  const [view, setView] = useState<"photo" | "corrected">("photo");
  const W = p.width;
  const H = p.height;
  const handleR = Math.max(13, W / 85);
  const font = Math.max(12, W / 62);
  const grid = p.calibration?.grid ?? [];
  const gridMap = useMemo(() => new Map(grid.map((g) => [g.hole, g])), [grid]);
  const pitch = p.calibration?.metrics?.pitch_px_min ?? W / 60;
  const canCorrect = p.mode === "calibrate" && !!p.rectifiedSrc && !!p.calibration?.rectified && p.calibration.status !== "failed";
  const showCorrected = canCorrect && view === "corrected";

  function toSvg(e: React.PointerEvent): Point {
    const svg = svgRef.current!;
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const m = svg.getScreenCTM()!.inverse();
    const r = pt.matrixTransform(m);
    return { x: clamp(r.x, 0, W), y: clamp(r.y, 0, H) };
  }

  function move(name: string, to: Point) {
    p.onLandmarksChange?.({ ...p.landmarks, [name]: to });
  }

  const poly = (pts: Point[]) => pts.map((q) => `${q.x},${q.y}`).join(" ");

  /* ---------- corrected (perspective-flattened) view ---------- */
  if (showCorrected && p.calibration?.rectified && p.columnOffsets) {
    const r = p.calibration.rectified;
    const cols = Object.entries(p.columnOffsets);
    return (
      <div>
        <ViewTabs view={view} setView={setView} canCorrect />
        <div className="frame">
          <svg viewBox={`0 0 ${r.width} ${r.height}`} role="img" aria-label="Perspective-corrected photo with the calibrated hole grid drawn on top">
            <image href={p.rectifiedSrc} x={0} y={0} width={r.width} height={r.height} />
            {Array.from({ length: 30 }, (_, i) => i + 1).flatMap((row) =>
              cols.map(([col, off]) => (
                <circle key={`${col}${row}`} cx={(r.margin_pitch + row - 1) * r.px_per_pitch} cy={(r.margin_pitch + off) * r.px_per_pitch} r={3} fill="#00e5ff" stroke="#003a42" strokeWidth={1} />
              )),
            )}
            {[1, 5, 10, 15, 20, 25, 30].map((row) => (
              <text key={row} x={(r.margin_pitch + row - 1) * r.px_per_pitch} y={r.px_per_pitch * 1.2} textAnchor="middle" fill="#fff" stroke="#000" strokeWidth={3} paintOrder="stroke" fontSize={15} fontWeight={700}>
                {row}
              </text>
            ))}
            {cols.map(([col, off]) => (
              <text key={col} x={r.px_per_pitch * 0.9} y={(r.margin_pitch + off) * r.px_per_pitch + 5} textAnchor="middle" fill="#fff" stroke="#000" strokeWidth={3} paintOrder="stroke" fontSize={15} fontWeight={700}>
                {col}
              </text>
            ))}
          </svg>
        </div>
        <p className="hint" style={{ marginTop: "0.5rem" }}>
          Corrected view: rows run left to right and every dot should sit on a hole. If dots drift from the holes, go back to the photo and nudge the corners.
        </p>
      </div>
    );
  }

  return (
    <div>
      {canCorrect ? <ViewTabs view={view} setView={setView} canCorrect /> : null}
      <div className="frame">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label="Photo of the assembled breadboard with analysis overlay"
          onPointerMove={(e) => {
            if (drag) move(drag, toSvg(e));
          }}
          onPointerUp={() => setDrag(null)}
          onPointerCancel={() => setDrag(null)}
          onClick={() => {
            if (p.mode === "observe") p.onSelectObs?.(null);
          }}
        >
          <image href={p.src} x={0} y={0} width={W} height={H} />

          {/* ----- calibration ----- */}
          {p.mode === "calibrate" && (
            <>
              {grid.map((g) => (
                <circle key={g.hole} cx={g.x} cy={g.y} r={Math.max(2.5, pitch * 0.13)} fill="#00e5ff" stroke="#003a42" strokeWidth={1} opacity={0.95} />
              ))}
              {LANDMARK_ORDER.every((k) => p.landmarks[k]) && (
                <polygon points={poly(LANDMARK_ORDER.map((k) => p.landmarks[k]))} fill="rgba(36,70,200,0.08)" stroke="#fff" strokeWidth={5} strokeLinejoin="round" />
              )}
              {LANDMARK_ORDER.every((k) => p.landmarks[k]) && (
                <polygon points={poly(LANDMARK_ORDER.map((k) => p.landmarks[k]))} fill="none" stroke="var(--action)" strokeWidth={2.5} strokeDasharray="10 6" strokeLinejoin="round" />
              )}
              {LANDMARK_ORDER.map((k) => {
                const pt = p.landmarks[k];
                if (!pt) return null;
                return (
                  <g
                    key={k}
                    className="handle"
                    tabIndex={0}
                    role="slider"
                    aria-label={`Corner ${k}, ${LANDMARK_HELP[k]}. Drag, or use arrow keys to nudge; hold Shift for larger steps.`}
                    aria-valuetext={`x ${Math.round(pt.x)}, y ${Math.round(pt.y)}`}
                    onPointerDown={(e) => {
                      (e.target as Element).setPointerCapture?.(e.pointerId);
                      setDrag(k);
                      e.stopPropagation();
                    }}
                    onKeyDown={(e) => {
                      const step = e.shiftKey ? 10 : 1;
                      const d: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
                      if (d[e.key]) {
                        e.preventDefault();
                        move(k, { x: clamp(pt.x + d[e.key][0], 0, W), y: clamp(pt.y + d[e.key][1], 0, H) });
                      }
                    }}
                  >
                    <circle cx={pt.x} cy={pt.y} r={handleR + 4} fill="#fff" opacity={0.95} />
                    <circle cx={pt.x} cy={pt.y} r={handleR} fill="rgba(36,70,200,0.25)" stroke="var(--action)" strokeWidth={4} />
                    <line x1={pt.x - handleR - 8} x2={pt.x + handleR + 8} y1={pt.y} y2={pt.y} stroke="var(--action)" strokeWidth={2} />
                    <line y1={pt.y - handleR - 8} y2={pt.y + handleR + 8} x1={pt.x} x2={pt.x} stroke="var(--action)" strokeWidth={2} />
                    <text x={pt.x + handleR + 8} y={pt.y - handleR - 4} fontSize={font * 1.15} fontWeight={800} fill="#fff" stroke="var(--action)" strokeWidth={5} paintOrder="stroke">
                      {k}
                    </text>
                  </g>
                );
              })}
            </>
          )}

          {/* ----- observations ----- */}
          {p.mode === "observe" &&
            [...(p.observations ?? [])]
              .filter((o) => o.observation_type !== "board" && o.bounding_box_or_polygon.length >= 3)
              .sort((a, b) => Number(a.id === p.selectedObsId) - Number(b.id === p.selectedObsId))
              .map((o) => {
                const st = statusStyle(o);
                const sel = o.id === p.selectedObsId;
                const xs = o.bounding_box_or_polygon.map((q) => q.x);
                const ys = o.bounding_box_or_polygon.map((q) => q.y);
                const tx = Math.min(...xs);
                const ty = Math.min(...ys);
                const tag = `${st.glyph} ${sel ? o.display_name : shortTag(o)}`;
                const tagW = tag.length * font * 0.58 + 14;
                return (
                  <g
                    key={o.id}
                    opacity={st.op}
                    tabIndex={0}
                    role="button"
                    aria-label={`${o.display_name}, ${o.status}. Select to review.`}
                    aria-pressed={sel}
                    onClick={(e) => {
                      e.stopPropagation();
                      p.onSelectObs?.(o.id);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        p.onSelectObs?.(o.id);
                      }
                    }}
                    style={{ cursor: "pointer" }}
                  >
                    <polygon points={poly(o.bounding_box_or_polygon)} fill="none" stroke="#fff" strokeWidth={sel ? 9 : 6} strokeLinejoin="round" />
                    <polygon points={poly(o.bounding_box_or_polygon)} fill={st.fill} stroke={sel ? "var(--action)" : st.stroke} strokeWidth={sel ? 5 : 3.5} strokeDasharray={st.dash} strokeLinejoin="round" />
                    <rect x={tx} y={ty - font * 1.55} width={tagW} height={font * 1.45} rx={3} fill="#fff" stroke={sel ? "var(--action)" : st.stroke} strokeWidth={2} />
                    <text x={tx + 7} y={ty - font * 0.45} fontSize={font} fontWeight={700} fill="var(--ink)">
                      {tag}
                    </text>
                    {o.status !== "rejected" &&
                      Object.values(o.candidate_part_or_endpoint.endpoints).map((ep, i) => {
                        const pos = ep.kind === "breadboard_hole" && ep.hole ? gridMap.get(ep.hole) : ep.point ?? undefined;
                        if (!pos) return null;
                        const x = "hole" in pos ? pos.x : pos.x;
                        const y = pos.y;
                        return (
                          <g key={i}>
                            <circle cx={x} cy={y} r={Math.max(6, pitch * 0.34)} fill="none" stroke="#fff" strokeWidth={5} />
                            <circle cx={x} cy={y} r={Math.max(6, pitch * 0.34)} fill="none" stroke={sel ? "var(--action)" : st.stroke} strokeWidth={3} />
                            {sel && (
                              <text x={x + pitch * 0.5} y={y - pitch * 0.5} fontSize={font} fontWeight={800} fill="#fff" stroke="#000" strokeWidth={4} paintOrder="stroke">
                                {ep.kind === "board_pin" ? ep.board_pin : ep.hole}
                              </text>
                            )}
                          </g>
                        );
                      })}
                  </g>
                );
              })}

          {/* ----- findings ----- */}
          {p.mode === "findings" &&
            (p.findings ?? [])
              .filter((f) => f.image_region.length >= 3 && f.status !== "NOT CHECKED")
              .map((f) => {
                const focus = f.id === p.focusFindingId;
                const col = FINDING_COLOR[f.status];
                const xs = f.image_region.map((q) => q.x);
                const ys = f.image_region.map((q) => q.y);
                return (
                  <g
                    key={f.id}
                    tabIndex={0}
                    role="button"
                    aria-label={`${f.status}: ${f.title}`}
                    onClick={() => p.onFocusFinding?.(f.id)}
                    onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && p.onFocusFinding?.(f.id)}
                    style={{ cursor: "pointer" }}
                    opacity={p.focusFindingId && !focus ? 0.55 : 1}
                  >
                    <polygon points={poly(f.image_region)} fill="none" stroke="#fff" strokeWidth={focus ? 12 : 8} />
                    <polygon points={poly(f.image_region)} fill={f.status === "POSSIBLE MISMATCH" ? "rgba(216,57,47,0.18)" : "rgba(138,88,196,0.16)"} stroke={col} strokeWidth={focus ? 6 : 4} strokeDasharray={f.status === "NEEDS REVIEW" ? "9 6" : undefined} />
                    {focus && (
                      <g>
                        <rect x={Math.min(...xs)} y={Math.min(...ys) - font * 1.9} width={Math.min(W - Math.min(...xs), f.title.length * font * 0.55 + 18)} height={font * 1.7} rx={3} fill="#fff" stroke={col} strokeWidth={3} />
                        <text x={Math.min(...xs) + 8} y={Math.min(...ys) - font * 0.55} fontSize={font} fontWeight={800} fill="var(--ink)">
                          {f.title.length > 60 ? `${f.title.slice(0, 58)}…` : f.title}
                        </text>
                      </g>
                    )}
                  </g>
                );
              })}
        </svg>
      </div>
    </div>
  );
}

function ViewTabs({ view, setView, canCorrect }: { view: "photo" | "corrected"; setView: (v: "photo" | "corrected") => void; canCorrect: boolean }) {
  if (!canCorrect) return null;
  return (
    <div className="frame-tabs" role="group" aria-label="Photo view">
      <button type="button" className="tab" aria-pressed={view === "photo"} onClick={() => setView("photo")}>
        Original photo
      </button>
      <button type="button" className="tab" aria-pressed={view === "corrected"} onClick={() => setView("corrected")}>
        Corrected view
      </button>
    </div>
  );
}
