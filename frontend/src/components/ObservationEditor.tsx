import { useEffect, useMemo, useRef, useState } from "react";
import type { Candidate, Endpoint, Observation, TemplateDetail } from "@/lib/types";
import { Spinner } from "./ui";

const BANDS = ["black", "brown", "red", "orange", "yellow", "green", "blue", "violet", "grey", "white"];

type EndForm = { kind: "hole" | "pin"; value: string };

function toForm(ep?: Endpoint): EndForm {
  if (ep?.kind === "board_pin") return { kind: "pin", value: ep.board_pin ?? "" };
  return { kind: "hole", value: ep?.hole ?? "" };
}

type Props = {
  detail: TemplateDetail;
  /** null = adding a new observation by hand */
  observation: Observation | null;
  onClose: () => void;
  /** Resolves to an error message, or null when saved. */
  onSubmit: (candidate: Candidate, type: "component" | "wire") => Promise<string | null>;
};

export default function ObservationEditor({ detail, observation, onClose, onSubmit }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const existing = observation?.candidate_part_or_endpoint;
  const addable = Object.values(detail.parts).filter((p) => ["wire", "resistor", "led"].includes(p.kind));
  const [partId, setPartId] = useState<string>(existing?.part_id ?? addable[0]?.id ?? "jumper_wire");
  const part = detail.parts[partId];
  const board = Object.values(detail.parts).find((p) => p.kind === "dev_board");
  const pins = board?.terminals.map((t) => t.name) ?? [];

  const [ends, setEnds] = useState<Record<string, EndForm>>(() => {
    const out: Record<string, EndForm> = {};
    for (const t of detail.parts[existing?.part_id ?? partId]?.terminals ?? []) out[t.name] = toForm(existing?.endpoints?.[t.name]);
    return out;
  });
  const [bands, setBands] = useState<string[]>(existing?.color_bands?.slice(0, 3) ?? ["red", "red", "brown"]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
    return () => d?.close();
  }, []);

  // Switching the part type (manual add only) resets the terminal fields.
  const terminals = useMemo(() => part?.terminals.map((t) => t.name) ?? [], [part]);
  useEffect(() => {
    if (observation) return;
    setEnds(Object.fromEntries(terminals.map((t) => [t, { kind: "hole", value: "" } as EndForm])));
  }, [terminals, observation]);

  const unsupported = observation && !existing?.part_id;
  const isWire = part?.kind === "wire";

  async function save() {
    setError(null);
    for (const t of terminals) {
      if (!ends[t]?.value.trim()) return setError(`Enter where ${labelFor(t)} is plugged in.`);
    }
    const endpoints: Record<string, Endpoint> = {};
    for (const t of terminals) {
      const f = ends[t];
      endpoints[t] = f.kind === "pin" ? { kind: "board_pin", board_pin: f.value.trim() } : { kind: "breadboard_hole", hole: f.value.trim() };
    }
    const inst = detail.template.instances.find((i) => i.part_id === partId);
    const cand: Candidate = {
      ...(existing ?? {}),
      part_id: partId,
      template_ref: part.kind === "wire" ? null : inst?.ref ?? null,
      endpoints,
      color_bands: part.kind === "resistor" ? bands : existing?.color_bands ?? null,
      value_ohms: part.kind === "resistor" ? null : existing?.value_ohms ?? null, // value is re-derived from the confirmed bands
    };
    setSaving(true);
    const msg = await onSubmit(cand, part.kind === "wire" ? "wire" : "component");
    setSaving(false);
    if (msg) setError(msg);
  }

  function labelFor(t: string) {
    if (part?.kind === "resistor") return `resistor lead ${t}`;
    if (part?.kind === "wire") return t === "end_a" ? "wire end A" : "wire end B";
    return t;
  }

  return (
    <dialog ref={ref} onClose={onClose} onCancel={onClose} aria-labelledby="edit-title">
      <div className="dialog-body">
        <h2 id="edit-title">{observation ? `Correct: ${observation.display_name}` : "Add a part or wire you can see"}</h2>

        {unsupported ? (
          <>
            <p>
              This object is not in the supported catalog, so Wirewise cannot check it. Reject it if it is not part of the circuit, or add the matching catalog part by hand.
            </p>
            <div className="btn-row">
              <button className="btn" type="button" onClick={onClose}>Close</button>
            </div>
          </>
        ) : (
          <>
            {!observation && (
              <div className="field">
                <label htmlFor="part-kind">What is it?</label>
                <select id="part-kind" className="select" value={partId} onChange={(e) => setPartId(e.target.value)}>
                  {addable.map((p) => (
                    <option key={p.id} value={p.id}>{p.display_name}</option>
                  ))}
                </select>
              </div>
            )}
            <p className="hint">
              Type the hole you can read on the board (column a–j, row 1–30, like <span className="hole">c10</span>).
              {isWire ? " A wire end that goes into the Arduino header uses the pin label." : ""}
            </p>

            <div className="form-grid">
              {terminals.map((t) => (
                <div className="field" key={t}>
                  <label htmlFor={`end-${t}`}>{labelFor(t)[0].toUpperCase() + labelFor(t).slice(1)}</label>
                  <div style={{ display: "grid", gridTemplateColumns: isWire ? "auto 1fr" : "1fr", gap: "0.4rem" }}>
                    {isWire && (
                      <select aria-label={`${labelFor(t)} location type`} className="select" value={ends[t]?.kind ?? "hole"} onChange={(e) => setEnds({ ...ends, [t]: { kind: e.target.value as "hole" | "pin", value: "" } })}>
                        <option value="hole">Breadboard</option>
                        <option value="pin">Arduino pin</option>
                      </select>
                    )}
                    <input
                      id={`end-${t}`}
                      className="input"
                      list={ends[t]?.kind === "pin" ? "board-pins" : undefined}
                      autoCapitalize="none"
                      autoComplete="off"
                      placeholder={ends[t]?.kind === "pin" ? "D9, GND …" : "a15"}
                      value={ends[t]?.value ?? ""}
                      onChange={(e) => setEnds({ ...ends, [t]: { ...(ends[t] ?? { kind: "hole" }), value: e.target.value } })}
                    />
                  </div>
                </div>
              ))}
            </div>
            <datalist id="board-pins">{pins.map((p) => <option key={p} value={p} />)}</datalist>

            {part?.kind === "resistor" && (
              <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
                <legend style={{ fontWeight: 600, marginBottom: 4 }}>Colour bands, first three</legend>
                <div className="form-grid" style={{ gridTemplateColumns: "repeat(3, minmax(0,1fr))" }}>
                  {bands.map((b, i) => (
                    <select key={i} className="select" aria-label={`Band ${i + 1}`} value={b} onChange={(e) => setBands(bands.map((x, j) => (j === i ? e.target.value : x)))}>
                      {BANDS.map((c) => <option key={c}>{c}</option>)}
                    </select>
                  ))}
                </div>
                <p className="hint" style={{ marginTop: 4 }}>Wirewise decodes the value from these bands using the standard colour code.</p>
              </fieldset>
            )}

            {error ? <p className="error-text" role="alert">{error}</p> : null}
            <div className="btn-row">
              <button className="btn btn-primary" type="button" onClick={save} disabled={saving}>
                {saving ? <Spinner label="Saving…" /> : observation ? "Save correction" : "Add observation"}
              </button>
              <button className="btn btn-quiet" type="button" onClick={onClose}>Cancel</button>
            </div>
          </>
        )}
      </div>
    </dialog>
  );
}
