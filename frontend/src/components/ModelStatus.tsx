import type { Health } from "@/lib/types";

/** Header status: provider, model name, and whether the model is reachable and loaded. */
export default function ModelStatus({ health, checking, onRecheck }: { health: Health | null; checking: boolean; onRecheck: () => void }) {
  if (!health) return null;
  let tone: "ok" | "warn" | "bad" = "bad";
  let icon = "✕";
  let headline: string;
  if (health.demo_mode) {
    tone = "warn";
    icon = "!";
    headline = "No model is running";
  } else if (!health.reachable) {
    headline = `${health.provider === "ollama" ? "Ollama" : "Gemini API"} not reachable`;
  } else if (!health.model_installed) {
    headline = "Model not installed";
  } else if (health.model_loaded) {
    tone = "ok";
    icon = "✓";
    headline = "Model loaded";
  } else {
    tone = "ok";
    icon = "○";
    headline = "Model ready (loads on first use)";
  }
  return (
    <div className="model-status" data-tone={tone} role="status" aria-live="polite">
      <span className="model-status-icon" aria-hidden>{icon}</span>
      <span>
        <strong>{health.demo_mode ? "DEMO" : "Gemma 4"}</strong>
        {health.model ? <> · <span className="mono">{health.model}</span></> : null}
        <span className="model-status-sub">
          {health.demo_mode ? "" : health.runtime ? `${health.runtime} · ` : ""}
          {headline}
        </span>
      </span>
      <button type="button" className="btn btn-small btn-quiet" onClick={onRecheck} disabled={checking} aria-label="Re-check model status">
        {checking ? "…" : "↻"}
      </button>
    </div>
  );
}
