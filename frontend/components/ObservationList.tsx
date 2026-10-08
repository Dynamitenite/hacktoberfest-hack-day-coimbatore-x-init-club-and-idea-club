"use client";

import type { Observation } from "@/lib/types";
import { ConfidenceBadge, endpointText, SourceBadge, StatusBadge } from "./ui";

type Props = {
  observations: Observation[];
  selectedId: string | null;
  busyId: string | null;
  onSelect: (id: string) => void;
  onAct: (id: string, action: "confirm" | "reject" | "reset") => void;
  onEdit: (o: Observation) => void;
  onRemove: (o: Observation) => void;
  onAdd: () => void;
};

const TERMINAL_LABEL: Record<string, string> = { end_a: "End A", end_b: "End B", "1": "Lead 1", "2": "Lead 2", anode: "Anode (+)", cathode: "Cathode (−)" };

function Card({ o, selected, busy, onSelect, onAct, onEdit, onRemove }: { o: Observation; selected: boolean; busy: boolean } & Omit<Props, "observations" | "selectedId" | "busyId" | "onAdd">) {
  const c = o.candidate_part_or_endpoint;
  const eps = Object.entries(c.endpoints);
  const reviewable = o.observation_type === "component" || o.observation_type === "wire";
  const canCorrect = reviewable && !!c.part_id;
  return (
    <li className="obs" data-status={o.status} data-selected={selected} id={`obs-${o.id}`}>
      <div className="obs-top">
        <button className="obs-name" type="button" onClick={() => onSelect(o.id)} aria-pressed={selected}>
          {o.display_name || "Unnamed observation"}
        </button>
        <StatusBadge status={o.status} />
      </div>
      <div className="obs-top" style={{ marginTop: 6 }}>
        <SourceBadge source={o.source} />
        <ConfidenceBadge level={o.confidence_label} />
      </div>

      {eps.length > 0 && (
        <dl className="obs-ends" style={{ margin: "0.45rem 0" }}>
          {eps.map(([t, ep]) => (
            <div key={t} style={{ display: "flex", gap: 6, alignItems: "baseline" }}>
              <dt className="muted">{TERMINAL_LABEL[t] ?? t}</dt>
              <dd style={{ margin: 0 }}>
                {ep.kind === "breadboard_hole" ? <span className="hole">{endpointText(ep)}</span> : <span>{endpointText(ep)}</span>}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {c.color_bands?.length ? <p className="small muted">Colour bands read: {c.color_bands.join(", ")}</p> : null}
      {c.orientation_note ? <p className="small muted">Polarity cue: {c.orientation_note}</p> : null}
      {c.description ? <p className="small muted">{c.description}</p> : null}
      {o.original_candidate ? <p className="small muted">Changed from the original proposal. “Undo” restores it.</p> : null}

      {reviewable && (
        <div className="obs-actions">
          {(o.status === "proposed" || o.status === "rejected") && (
            <button className="btn btn-small btn-primary" type="button" disabled={busy} onClick={() => onAct(o.id, "confirm")}>
              Confirm
            </button>
          )}
          {o.status !== "rejected" && (
            <button className="btn btn-small btn-danger" type="button" disabled={busy} onClick={() => onAct(o.id, "reject")}>
              Reject
            </button>
          )}
          {canCorrect && (
            <button className="btn btn-small" type="button" disabled={busy} onClick={() => onEdit(o)}>
              Correct…
            </button>
          )}
          {o.status === "rejected" || o.original_candidate ? (
            <button className="btn btn-small btn-quiet" type="button" disabled={busy} onClick={() => onAct(o.id, "reset")}>
              Undo
            </button>
          ) : null}
          {o.source === "user" && !o.original_candidate ? (
            <button className="btn btn-small btn-quiet" type="button" disabled={busy} onClick={() => onRemove(o)}>
              Remove
            </button>
          ) : null}
        </div>
      )}

      <details className="evidence">
        <summary>Where this came from ({o.evidence.length})</summary>
        <ul>
          {o.evidence.map((e, i) => (
            <li key={i}>
              <span className="src">{e.source}</span>: {e.note}
            </li>
          ))}
        </ul>
      </details>
    </li>
  );
}

export default function ObservationList(props: Props) {
  const { observations, selectedId, busyId, onAdd } = props;
  const list = observations.filter((o) => o.observation_type !== "board");
  const reviewable = list.filter((o) => o.observation_type === "component" || o.observation_type === "wire");
  const done = reviewable.filter((o) => o.status !== "proposed").length;
  const parts = list.filter((o) => o.observation_type === "component");
  const wires = list.filter((o) => o.observation_type === "wire");
  const other = list.filter((o) => o.observation_type !== "component" && o.observation_type !== "wire");

  const render = (title: string, items: Observation[]) =>
    items.length ? (
      <section aria-label={title} style={{ display: "grid", gap: 8 }}>
        <h3>{title}</h3>
        <ul className="obs-list">
          {items.map((o) => (
            <Card key={o.id} o={o} selected={o.id === selectedId} busy={busyId === o.id} onSelect={props.onSelect} onAct={props.onAct} onEdit={props.onEdit} onRemove={props.onRemove} />
          ))}
        </ul>
      </section>
    ) : null;

  return (
    <div className="stack" style={{ gap: "1rem" }}>
      <div className="panel-head" style={{ marginBottom: 0 }}>
        <p aria-live="polite">
          <strong>{done} of {reviewable.length}</strong> reviewed
          {done < reviewable.length ? <span className="muted"> · proposals are not facts until you confirm them</span> : null}
        </p>
        <button className="btn btn-small" type="button" onClick={onAdd}>Add a part or wire</button>
      </div>
      {list.length === 0 ? (
        <div className="empty">
          <p><strong>No observations yet.</strong></p>
          <p className="small">Run the analysis, or add what you can see by hand.</p>
        </div>
      ) : (
        <>
          {render("Parts", parts)}
          {render("Wires", wires)}
          {render("Unclear areas", other)}
        </>
      )}
    </div>
  );
}
