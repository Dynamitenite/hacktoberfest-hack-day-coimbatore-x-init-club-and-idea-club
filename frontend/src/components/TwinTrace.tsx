import type { EdgeCheck, Report } from "@/lib/types";

/**
 * Expected connection above, observed connection below. When the two terminals do not share
 * a net, each side shows the breadboard strip it was actually confirmed in, with the break marked.
 */
function stripsFor(report: Report, nodeId: string): string[] {
  const g = report.observed_graph;
  if (!g.nodes.some((n) => n.id === nodeId)) return [];
  const adj = new Map<string, string[]>();
  for (const e of g.edges) {
    adj.set(e.a, [...(adj.get(e.a) ?? []), e.b]);
    adj.set(e.b, [...(adj.get(e.b) ?? []), e.a]);
  }
  const seen = new Set([nodeId]);
  const queue = [nodeId];
  while (queue.length) {
    const cur = queue.shift()!;
    for (const nb of adj.get(cur) ?? []) if (!seen.has(nb)) (seen.add(nb), queue.push(nb));
  }
  return g.nodes.filter((n) => n.kind === "strip" && seen.has(n.id)).map((n) => n.label);
}

export default function TwinTrace({ report, check, a, b }: { report: Report; check: EdgeCheck; a: string; b: string }) {
  const label = (id: string) => report.expected_graph.nodes.find((n) => n.id === id)?.label ?? id;
  const matched = check.state === "MATCHES TEMPLATE";
  const sa = stripsFor(report, a);
  const sb = stripsFor(report, b);
  return (
    <div className="twin" role="group" aria-label={`Expected versus observed: ${label(a)} to ${label(b)}`}>
      <span className="twin-row-label">Template expects</span>
      <span className="twin-node">{label(a)}</span>
      <span className="twin-line" aria-hidden />
      <span className="twin-node">{label(b)}</span>

      <span className="twin-row-label">{matched ? "You confirmed a path" : "What you confirmed"}</span>
      <span className="twin-node" style={{ borderColor: matched ? "var(--ok-line)" : "var(--bad-line)" }}>{label(a)}</span>
      {matched ? (
        <span className="twin-obs">
          <span className="twin-seg" />
          <span className="twin-strip">{sa[0] ?? "wired"}</span>
          <span className="twin-seg" />
        </span>
      ) : (
        <span className="twin-obs">
          <span className="twin-seg" data-unseen={sa.length === 0} />
          <span className="twin-strip">{sa.length ? sa.join(", ") : "nothing confirmed"}</span>
          <span className="twin-gap" aria-label="break">╳</span>
          <span className="twin-strip">{sb.length ? sb.join(", ") : "nothing confirmed"}</span>
          <span className="twin-seg" data-unseen={sb.length === 0} />
        </span>
      )}
      <span className="twin-node" style={{ borderColor: matched ? "var(--ok-line)" : "var(--bad-line)" }}>{label(b)}</span>
    </div>
  );
}
