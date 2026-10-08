import type { Confidence, Endpoint, ObsStatus, ResultState, Source } from "@/lib/types";

const STATE_TONE: Record<ResultState, string> = {
  "MATCHES TEMPLATE": "ok",
  "POSSIBLE MISMATCH": "bad",
  "NEEDS REVIEW": "review",
  "NOT CHECKED": "skip",
};
const STATE_ICON: Record<ResultState, string> = {
  "MATCHES TEMPLATE": "✓",
  "POSSIBLE MISMATCH": "✕",
  "NEEDS REVIEW": "?",
  "NOT CHECKED": "–",
};

export function StateBadge({ state }: { state: ResultState }) {
  return (
    <span className="badge" data-tone={STATE_TONE[state]}>
      <span aria-hidden>{STATE_ICON[state]}</span>
      {state}
    </span>
  );
}

export const SOURCE_LABEL: Record<Source, string> = {
  gemma: "Gemma 4 proposed",
  demo: "Demo fixture",
  opencv: "OpenCV",
  user: "You",
};

export function SourceBadge({ source }: { source: Source }) {
  const tone = source === "demo" ? "warn" : source === "user" ? "ok" : "plain";
  return (
    <span className="badge" data-tone={tone} title="Where this observation came from">
      {SOURCE_LABEL[source]}
    </span>
  );
}

const STATUS_TEXT: Record<ObsStatus, { text: string; tone: string; icon: string }> = {
  proposed: { text: "Proposed, needs your review", tone: "warn", icon: "◌" },
  confirmed: { text: "Confirmed", tone: "ok", icon: "✓" },
  corrected: { text: "Corrected by you", tone: "ok", icon: "✎" },
  rejected: { text: "Rejected", tone: "skip", icon: "✕" },
};

export function StatusBadge({ status }: { status: ObsStatus }) {
  const s = STATUS_TEXT[status];
  return (
    <span className={status === "proposed" ? "badge badge-dashed" : "badge"} data-tone={s.tone}>
      <span aria-hidden>{s.icon}</span>
      {s.text}
    </span>
  );
}

export function ConfidenceBadge({ level }: { level: Confidence }) {
  const label = level === "uncertain" ? "Uncertain" : `${level[0].toUpperCase()}${level.slice(1)} confidence`;
  const tone = level === "high" ? "plain" : "warn";
  return (
    <span className="badge" data-tone={tone}>
      {level === "uncertain" || level === "low" ? <span aria-hidden>?</span> : null}
      {label}
    </span>
  );
}

export function endpointText(ep?: Endpoint | null): string {
  if (!ep) return "not located";
  switch (ep.kind) {
    case "breadboard_hole":
      return ep.hole ?? "hole not read";
    case "board_pin":
      return ep.board_pin ? `Arduino ${ep.board_pin}` : "Arduino pin not read";
    case "power_rail":
      return "power rail (not checked)";
    case "off_grid":
      return "outside the grid";
    default:
      return "not located";
  }
}

export function Spinner({ label }: { label: string }) {
  return (
    <>
      <span className="spinner" aria-hidden />
      <span>{label}</span>
    </>
  );
}
