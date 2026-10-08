"use client";

import type { Finding, Report, TemplateDetail } from "@/lib/types";
import TwinTrace from "./TwinTrace";
import { SOURCE_LABEL, StateBadge } from "./ui";

type Props = {
  report: Report;
  detail: TemplateDetail;
  focusId: string | null;
  onFocus: (id: string, target: "photo" | "schematic") => void;
  onCorrect: (obsId: string) => void;
  editableObs: Set<string>;
};

const TYPE_LABEL: Record<string, string> = {
  missing_connection: "Missing connection",
  unexpected_connection: "Unexpected connection",
  wrong_row: "Wrong row",
  wrong_pin: "Wrong pin",
  polarity_mismatch: "Polarity",
  value_mismatch: "Part value",
  ambiguous: "Ambiguous",
  not_checked: "Not checked",
};

function FindingCard({ f, p }: { f: Finding; p: Props }) {
  const rules = f.rule_ids.map((id) => ({ id, text: p.detail.template.explicit_rules.find((r) => r.id === id)?.text ?? (id.startsWith("breadboard:") ? "Breadboard connectivity model" : id) }));
  const edge = f.expected_edge_ids[0] ? p.report.edge_checks.find((c) => c.edge_id === f.expected_edge_ids[0]) : undefined;
  const edgeDef = f.expected_edge_ids[0] ? p.detail.template.expected_edges.find((e) => e.id === f.expected_edge_ids[0]) : undefined;
  const fixable = f.source_observation_ids.find((id) => p.editableObs.has(id));
  const hasRegion = f.image_region.length >= 3;
  return (
    <li className="finding" data-state={f.status} data-focus={p.focusId === f.id} id={`finding-${f.id}`}>
      <div className="obs-top">
        <StateBadge state={f.status} />
        <span className="chip">{TYPE_LABEL[f.finding_type] ?? f.finding_type}</span>
      </div>
      <h3 className="finding-title" style={{ marginTop: 6 }}>{f.title}</h3>

      {(f.expected_connection || f.observed_connection) && (
        <dl className="compare">
          {f.expected_connection && (<><dt>Template expects</dt><dd>{f.expected_connection}</dd></>)}
          {f.observed_connection && (<><dt>You confirmed</dt><dd>{f.observed_connection}</dd></>)}
        </dl>
      )}
      {edge && edgeDef && f.status !== "NOT CHECKED" ? <TwinTrace report={p.report} check={edge} a={edgeDef.a} b={edgeDef.b} /> : null}

      <p style={{ marginTop: 8 }}>{f.explanation}</p>
      {f.suggestion ? <p className="small muted" style={{ marginTop: 4 }}><strong>Try:</strong> {f.suggestion}</p> : null}

      <div className="chips" aria-label="Evidence and rules used">
        {f.evidence.map((e, i) => (
          <span className="chip" key={i} title={e.note}>
            {(SOURCE_LABEL as Record<string, string>)[e.source] ?? e.source}: {e.note.length > 56 ? `${e.note.slice(0, 54)}…` : e.note}
          </span>
        ))}
        {rules.map((r) => (
          <span className="chip" key={r.id} title={r.text}>Rule: {r.text.length > 52 ? `${r.text.slice(0, 50)}…` : r.text}</span>
        ))}
      </div>

      <div className="obs-actions">
        {hasRegion && <button className="btn btn-small" type="button" onClick={() => p.onFocus(f.id, "photo")}>Show on photo</button>}
        {f.expected_edge_ids.length > 0 && <button className="btn btn-small" type="button" onClick={() => p.onFocus(f.id, "schematic")}>Show expected link</button>}
        {fixable && <button className="btn btn-small btn-primary" type="button" onClick={() => p.onCorrect(fixable)}>Correct this connection</button>}
      </div>
    </li>
  );
}

export default function FindingsPanel(p: Props) {
  const { report } = p;
  const mism = report.findings.filter((f) => f.status === "POSSIBLE MISMATCH");
  const review = report.findings.filter((f) => f.status === "NEEDS REVIEW");
  const skipped = report.findings.filter((f) => f.status === "NOT CHECKED");
  const group = (title: string, items: Finding[]) =>
    items.length ? (
      <section aria-label={title}>
        <div className="group-title"><h2>{title}</h2><span className="badge" data-tone="plain">{items.length}</span></div>
        <ul className="obs-list">{items.map((f) => <FindingCard key={f.id} f={f} p={p} />)}</ul>
      </section>
    ) : null;

  return (
    <div className="stack" style={{ gap: "0.25rem" }}>
      <div className="verdict" data-state={report.overall_status} role="status">
        <div className="obs-top"><StateBadge state={report.overall_status} /><span className="small muted">{report.counts.edges_matched} of {report.counts.edges_total} expected connections matched</span></div>
        <p className="verdict-title" style={{ marginTop: 6 }}>{report.headline}</p>
        <p className="disclaimer">{report.disclaimer}</p>
      </div>

      {group("Possible mismatches", mism)}
      {group("Needs review", review)}

      <section aria-label="Every expected connection">
        <div className="group-title"><h2>Expected connections</h2></div>
        <ul className="obs-list">
          {report.edge_checks.map((c) => {
            const def = p.detail.template.expected_edges.find((e) => e.id === c.edge_id)!;
            return (
              <li key={c.edge_id} className="finding" data-state={c.state} data-focus={false}>
                <div className="obs-top"><StateBadge state={c.state} /><strong>{c.expected}</strong></div>
                <TwinTrace report={report} check={c} a={def.a} b={def.b} />
                <p className="small muted" style={{ marginTop: 6 }}>Rule: {p.detail.template.explicit_rules.find((r) => r.id === c.rule_id)?.text}</p>
              </li>
            );
          })}
        </ul>
      </section>

      {skipped.length > 0 && (
        <details style={{ marginTop: "1rem" }}>
          <summary style={{ cursor: "pointer", fontWeight: 700 }}>Not checked ({skipped.length})</summary>
          <ul className="obs-list" style={{ marginTop: 8 }}>{skipped.map((f) => <FindingCard key={f.id} f={f} p={p} />)}</ul>
        </details>
      )}
      <p className="small muted" style={{ marginTop: "0.8rem" }}>{report.comparison_method}</p>
    </div>
  );
}
