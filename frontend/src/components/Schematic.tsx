import type { Diagram, EdgeCheck, ResultState } from "@/lib/types";

type Props = {
  diagram: Diagram;
  /** Per expected edge: how the last comparison judged it. Omit before a report exists. */
  edgeChecks?: EdgeCheck[];
  /** Edge ids to emphasise (e.g. from a selected finding). */
  focusEdgeIds?: string[];
  title?: string;
};

function zigzag(x1: number, y: number, x2: number): string {
  const pad = 16;
  const a = x1 + pad;
  const b = x2 - pad;
  const n = 6;
  const step = (b - a) / n;
  let d = `M${x1},${y} L${a},${y}`;
  for (let i = 0; i < n; i++) d += ` L${a + step * (i + 0.5)},${y + (i % 2 === 0 ? -11 : 11)}`;
  return `${d} L${b},${y} L${x2},${y}`;
}

export default function Schematic({ diagram, edgeChecks, focusEdgeIds = [], title = "Intended circuit" }: Props) {
  const stateOf = (id: string): ResultState | undefined => edgeChecks?.find((c) => c.edge_id === id)?.state;
  return (
    <figure className="schematic" style={{ margin: 0 }}>
      <svg viewBox={diagram.viewBox} role="img" aria-label={`${title}: schematic generated from the template`}>
        <title>{title}</title>
        {diagram.wires.map((w) => (
          <polyline
            key={w.edge_id}
            className="sch-wire"
            data-edge={w.edge_id}
            data-state={stateOf(w.edge_id)}
            data-focus={focusEdgeIds.includes(w.edge_id)}
            points={w.points.map((p) => p.join(",")).join(" ")}
          />
        ))}
        {diagram.symbols.map((s) => {
          if (s.type === "board") {
            return (
              <g key={s.id}>
                <rect x={s.x} y={s.y} width={s.w} height={s.h} rx={4} fill="#d8ecea" stroke="#15262b" strokeWidth={2.5} />
                <text className="sch-text" x={(s.x ?? 0) + 10} y={(s.y ?? 0) + 24} fontWeight={700}>
                  {s.label}
                </text>
                {s.pins?.map((p) => (
                  <g key={p.terminal}>
                    <circle className="sch-pin" cx={p.x} cy={p.y} r={5} />
                    <text className="sch-text" x={p.x - 12} y={p.y - 9} textAnchor="end" fontWeight={600}>
                      {p.label}
                    </text>
                  </g>
                ))}
              </g>
            );
          }
          if (s.type === "resistor") {
            const y = s.y1 ?? 0;
            return (
              <g key={s.id}>
                <path d={zigzag(s.x1 ?? 0, y, s.x2 ?? 0)} fill="none" stroke="#15262b" strokeWidth={3} strokeLinejoin="round" />
                <text className="sch-text" x={((s.x1 ?? 0) + (s.x2 ?? 0)) / 2} y={y - 22} textAnchor="middle" fontWeight={600}>
                  {s.label}
                </text>
                <text className="sch-text" x={(s.x1 ?? 0) + 2} y={y + 28} style={{ fontSize: 11 }} fill="#44585e">lead 1</text>
                <text className="sch-text" x={(s.x2 ?? 0) - 2} y={y + 28} textAnchor="end" style={{ fontSize: 11 }} fill="#44585e">lead 2</text>
              </g>
            );
          }
          // LED: anode on top, cathode at the bottom, triangle points anode → cathode
          const x = s.x1 ?? 0;
          const top = s.y1 ?? 0;
          const bot = s.y2 ?? 0;
          const mid = (top + bot) / 2;
          return (
            <g key={s.id}>
              <line x1={x} y1={top} x2={x} y2={mid - 14} stroke="#15262b" strokeWidth={3} />
              <polygon points={`${x - 16},${mid - 14} ${x + 16},${mid - 14} ${x},${mid + 14}`} fill="#ffd9d6" stroke="#15262b" strokeWidth={3} strokeLinejoin="round" />
              <line x1={x - 16} y1={mid + 14} x2={x + 16} y2={mid + 14} stroke="#15262b" strokeWidth={3} />
              <line x1={x} y1={mid + 14} x2={x} y2={bot} stroke="#15262b" strokeWidth={3} />
              <path d={`M${x + 22},${mid - 10} l10,-10 m-2,0 h2 v2`} fill="none" stroke="#b02a25" strokeWidth={2} />
              <path d={`M${x + 28},${mid + 2} l10,-10 m-2,0 h2 v2`} fill="none" stroke="#b02a25" strokeWidth={2} />
              <text className="sch-text" x={x + 26} y={top - 4} fontWeight={600}>{s.label} anode (+)</text>
              <text className="sch-text" x={x + 26} y={bot + 16} fontWeight={600}>cathode (−)</text>
            </g>
          );
        })}
      </svg>
    </figure>
  );
}
