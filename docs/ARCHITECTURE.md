# Wirewise architecture

```
Browser (Next.js, React)
  │  /api/*  (same origin; next.config.ts rewrites to BACKEND_URL)
  ▼
FastAPI backend ──► session store (memory, sliding TTL; photo bytes live here)
  │                 SQLite (templates, explicitly saved projects)
  ├─ image_processing  validate → normalise → calibrate → rectify
  ├─ vision_provider   Gemma 4 | demo → RawProposals → normalize()
  ├─ circuit_graph     confirmed observations → NetworkX graph (+ provenance)
  └─ comparison        expected graph vs observed graph → Report
```

## Principle: the model proposes, the user confirms, code decides

| Stage | Who | Output |
| --- | --- | --- |
| Calibrate | User (4 handles) + OpenCV | Homography, grid, validity score |
| Propose | Gemma 4 or demo provider | `RawProposals` (kind, box, confidence, endpoints) |
| Normalise | Python | `Observation`s, endpoints snapped to nearest calibrated hole, kinds mapped through a closed catalog mapping |
| Confirm | User | `confirmed`, `rejected` or `corrected` status |
| Compare | NetworkX + template rules | `Finding`s and an overall state |

Rejected and unreviewed observations never create graph edges. The comparison module has no access to the vision provider.

## Backend modules (`backend/app`)

- `schemas.py`: Pydantic models for `CircuitTemplate`, `PartCatalogItem`, `ImageSession`, `Observation`, `Connection`, `Finding`, `Report`. Observation `source` is `gemma`, `opencv`, `user`, or `demo`; scripted demo output is never labelled Gemma.
- `catalog.py`: loads and validates `data/catalog/parts.json` and `data/templates/*.json`. A template that references a part missing from the catalog is rejected at load. Also holds hole parsing, strip ids, the resistor colour-code decoder (IEC 60062) and Ω formatting.
- `image_processing.py`: type, size and pixel-count validation; EXIF transpose; re-encode to JPEG (drops metadata); downscale. Calibration uses `cv2.getPerspectiveTransform` on four landmarks in pitch units, then checks quad convexity, pitch size, side ratios, and hole contrast against a half-pitch "phantom" grid so a shifted grid is caught. `rectify` warps to a top-down view; `annotate_for_model` draws row numbers and column letters into the margin for the model.
- `vision_provider/`: `gemma.py` (Gemini API, Files API upload then delete, system prompt marks the image as untrusted, API key scrubbed from errors), `demo.py` (replays fixture proposals; matches by fixture id or by normalised image correlation; refuses unknown photos), `normalize.py` (the single path both providers go through, so the demo exercises the real pipeline).
- `circuit_graph.py`: builds the expected graph from the template and the observed graph from confirmed observations. Nodes are terminals, board pins, holes and breadboard strips. Every node and edge carries provenance such as `gemma:confirmed` or `user:corrected`.
- `comparison.py`: edge-by-edge check against template rules, then findings.
- `storage.py`: in-memory `SessionStore` and SQLite `Database`.
- `main.py`: REST API.

### Breadboard model

Half-size 400: rows 1–30, columns a–j. Holes a–e in one row are one strip, f–j another; the centre channel isolates them. Power rails are not modelled, so anything that depends on them is `NOT CHECKED`.

### Findings and states

Finding types: `wrong_row`, `wrong_pin`, `polarity_mismatch` (found by a swap test), `missing_connection`, `unexpected_connection` (bridged nets), `value_mismatch` (colour bands decoded and compared with the template rule), `ambiguous`, `not_checked`.

Overall state: any possible mismatch → `POSSIBLE MISMATCH`; otherwise unreviewed catalog-mapped proposals, missing parts or low-confidence or unverified calibration → `NEEDS REVIEW`; otherwise `MATCHES TEMPLATE`. `NOT CHECKED` marks things Wirewise cannot judge at all, such as power rails. Every report includes a standing disclaimer and a list of what was not checked.

## Safety and privacy decisions

- No claim of safety anywhere; `MATCHES TEMPLATE` is worded as "the confirmed connections match". There is a test that scans report text.
- No hardware control code. No USB, serial, Bluetooth or network commands to devices.
- Text inside an image is treated as data. Proposal text is cleaned (control characters stripped, 120-character cap) and rendered as plain text.
- Ratings and pinouts come only from the catalog, with a source per part. No electrical limits are stored.
- The Gemini key is read in `config.py` on the server. The browser sees only same-origin `/api` calls.
- Photos are held in memory for the session (sliding TTL). They reach disk only when the user clicks **Save project**, which writes to `data/saved/`.

## Frontend (`frontend`)

- Next.js App Router, TypeScript, plain CSS with tokens (`app/globals.css`).
- `WirewiseApp.tsx`: the three steps and shared state.
- `PhotoCanvas.tsx`: SVG over the photo with draggable, keyboard-operable landmark handles, grid dots, observation outlines and finding regions. Status uses shape and dash patterns as well as colour.
- `Schematic.tsx`: template diagram with edges coloured and patterned by state.
- `TwinTrace.tsx`: expected connection above the confirmed one, with the break marked.
- `ObservationList.tsx`, `ObservationEditor.tsx`, `FindingsPanel.tsx`: review and findings UI.

## Adding a circuit

1. Add any new parts, with sources, to `backend/data/catalog/parts.json`.
2. Add `backend/data/templates/<id>.json` with instances, expected edges, explicit rules and a reference layout and diagram.
3. Add a fixture (photo plus `proposals.json`) if you want it to work in demo mode.
4. Add comparison tests beside `backend/tests/test_comparison.py`.
