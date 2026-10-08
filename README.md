# Wirewise

**Check your breadboard against the circuit you meant to build.**

Wirewise compares a photo of a real low-voltage breadboard circuit with an intended circuit template. Gemma 4 looks at the photo and *proposes* what it sees. You confirm, reject or correct each proposal. A deterministic graph comparison then reports where the confirmed wiring differs from the template, with the evidence for every finding.

It is an inspection and learning aid. It never powers, controls or talks to hardware, and it never says a circuit is safe to power.

## The problem

A wire one row off, a swapped LED, or the wrong resistor is easy to miss on a breadboard, and a photo is how makers ask for help. A language model alone can be confidently wrong about a photo. Wirewise keeps the model in the role it is good at (proposing what is visible) and puts the verdict in code that can be tested: confirmed observations in, template rules out, every finding traceable.

## What it does

1. **Choose a circuit.** One verified template ships: an Arduino UNO R3 pin D9 driving a 5 mm red LED through a 220 Ω resistor, on a half-size 400-point breadboard. You see the schematic and the expected connection list.
2. **Inspect your photo.** Upload a JPEG, PNG or WebP (type and size are validated). Drag four corner handles onto breadboard holes `a1`, `a30`, `j30`, `j1`. Wirewise computes a perspective correction, draws a hole grid over the photo and checks that the grid really lands on holes. If it does not, it asks you to adjust instead of guessing.
3. **Review proposals.** Gemma 4 proposes parts and wire endpoints with a bounding polygon and a confidence label. Each proposal shows its origin (`gemma`, `opencv`, `user` or `demo`). Proposals are not facts until you confirm them. You can reject, correct hole or pin positions, or add something the model missed.
4. **Review findings.** A graph is built only from confirmed observations. NetworkX compares it with the template. The report shows one of four states:
   - `MATCHES TEMPLATE`
   - `POSSIBLE MISMATCH`
   - `NEEDS REVIEW`
   - `NOT CHECKED`

   Findings are grouped, each with the evidence used, the rule applied, a "Show on photo" jump to the region, and a "Show expected link" jump to the schematic. A twin-trace view puts the expected connection above what you confirmed, with the break marked.

Finding types: wrong row, wrong pin, polarity mismatch, missing connection, unexpected connection, resistor value mismatch (from colour bands you confirmed), ambiguous, and not checked.

## Quick start (demo mode, no API key)

Requirements: Python 3.11+ and Node.js 20+.

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000

# 2. Frontend (second terminal)
cd frontend
npm install
npm run build && npm start        # or: npm run dev
```

Open http://localhost:3000. A banner makes demo mode obvious. With no `GEMINI_API_KEY` the app uses the demo provider, which replays recorded proposals for the two bundled demo photos and refuses any other photo.

The browser only talks to the Next.js server. `next.config.ts` proxies `/api/*` to `BACKEND_URL` (default `http://127.0.0.1:8000`), so no key and no backend address are in browser code.

## Using Gemma 4

```bash
cp .env.example .env      # then set GEMINI_API_KEY
```

With a key set, Wirewise offers Gemma 4 as the photo provider. The backend uses:

- **Integration:** the Gemini API through the `google-genai` Python SDK (server side only).
- **Model:** `gemma-4-31b-it` by default; `gemma-4-26b-a4b-it` is also allowed through `GEMMA_MODEL`.
- **Image input:** the Files API (`client.files.upload`), with the image placed before the text prompt, deleted again right after the call. `GEMMA_IMAGE_INPUT=inline` sends bytes in the request instead.
- **Output:** a fenced JSON block with `box_2d` boxes on a 0–1000 grid (`[ymin, xmin, ymax, xmax]`), parsed and validated with Pydantic. JSON mode is not relied on.

The integration was written against the Gemma on Gemini API and Gemma vision docs on 2026-10-08. **The Gemma path has been tested with a fake client in the test suite, not against the live API**, so check the model ID and image-input method against the current docs if a call fails.

### How Gemma 4 contributes

Gemma 4 does the part that needs vision: finding resistors, LEDs, jumper wires and the Arduino in the rectified photo, reading resistor colour bands, and describing which hole or header pin each wire end or lead appears to use. It does not make the pass/fail call, never supplies ratings or pinouts, and its output is treated as untrusted. Positions are snapped to the nearest calibrated hole by OpenCV; text visible in the image is never obeyed.

## Supported hardware

| Item | Supported |
| --- | --- |
| Circuit | `uno_d9_led_220r`: D9 → 220 Ω resistor → red LED anode, LED cathode → GND |
| Board | Arduino UNO R3 (header pins D8, D9, D10, GND, 5V, 3V3 in the catalog) |
| Breadboard | Half-size 400-point, 30 rows, columns a–e and f–j, centre channel isolates |
| Parts | 220 Ω resistor (red-red-brown), 5 mm red LED, jumper wire |

Catalog facts (pinouts, polarity cues, colour code) come from `backend/data/catalog/parts.json` with a source listed per part. Wirewise stores no voltage or current limits and never takes them from model memory.

## Limitations

- One circuit, one breadboard model. Other photos can be analysed only if they match this hardware.
- Power rails are not modelled; anything depending on them is `NOT CHECKED`.
- It only sees what is visible and confirmed. Hidden or out-of-frame wiring, damaged parts, bad contacts, voltages and currents are not checked.
- Calibration is manual and assumes a roughly top-down photo of the whole board. Heavy glare, blur or a tilted board can fail the grid check.
- The two demo photos are **synthetic renders**, not photographs of real hardware. The demo provider only works on them.
- `MATCHES TEMPLATE` means the confirmed connections match the template. It is not a safety statement.

## Demo script (about two minutes)

1. Open the app. Point out the demo banner and the first step: the schematic and expected connections.
2. Choose **Seeded mismatch: ground jumper in row 16**.
3. On the calibration screen, show the four pre-placed handles on `a1`, `a30`, `j30`, `j1`.
4. Click **Check the grid**: 99% of holes matched. Switch to **Corrected view** to show rows and columns lining up.
5. Click **Find parts and wires**. Proposals appear as dashed overlays with confidence labels and origins.
6. Confirm the resistor, LED and both wires. **Reject** the stray orange object (a capacitor decoy not in the template).
7. Click **Check against the template**: `POSSIBLE MISMATCH`, wrong row.
8. Click **Show on photo** (red region) and **Show expected link** (schematic). Read the twin trace: LED cathode in row 15, GND wire in row 16.
9. Click **Correct this connection**, change the wire end to `a15`, save.
10. The result becomes `MATCHES TEMPLATE`, still with the "not a safety statement" note. Optionally click **Save project**.

## Manual acceptance checklist

- [ ] The main flow works in demo mode with no API credentials.
- [ ] The demo banner is visible on every step in demo mode.
- [ ] The app never says a circuit is "safe to power" (search the UI and report for "safe").
- [ ] Uploading a PDF, an oversized file or a non-image is rejected with a clear message.
- [ ] A photo that cannot be calibrated asks for corner adjustment instead of continuing.
- [ ] Rejecting a proposal removes it from the comparison.
- [ ] Unreviewed proposals never produce a `MATCHES TEMPLATE` result.
- [ ] Every finding lists evidence and the rule used, and jumps to a photo region where one exists.
- [ ] Handles are movable by keyboard (arrow keys, Shift for 10 px); state is never colour-only.
- [ ] The layout is usable at 390 px width with no horizontal scroll.
- [ ] The frontend contains no API key; `GEMINI_API_KEY` appears only in help text naming the server variable.
- [ ] A photo is not on disk unless **Save project** was clicked.

## Tests

```bash
cd backend && pip install -r requirements-dev.txt && pytest      # 60 tests
cd frontend && npm run typecheck && npm run build
```

The suite covers: proposals and rejected observations never create edges; the report never contains "safe"; provenance on every node and edge; text injected into a proposal staying inert; the API key never appearing in responses or errors; the Files API upload being deleted after use; the demo provider refusing unknown photos; calibration failure modes; upload validation including EXIF stripping.

## Dependencies

Backend (`backend/requirements.txt`): FastAPI, Uvicorn, Pydantic, NetworkX, `google-genai`, `opencv-python-headless`, NumPy, Pillow, python-multipart. Dev: pytest and httpx.
Frontend (`frontend/package.json`): Next.js 16 (App Router), React 19, TypeScript, and the self-hosted fonts Bricolage Grotesque and Atkinson Hyperlegible Next via Fontsource.
Storage: SQLite (standard library) for templates and explicitly saved projects.

## Regenerating the demo fixtures

```bash
cd backend && python scripts/generate_fixtures.py
```

## Hackathon notes

Built for the Hacktoberfest Hack Day main track and the optional Gemma 4 challenge. Wirewise does not submit anything to MLH or OrganizerHQ; submit the repository yourself.

## License

Apache-2.0. See [LICENSE](LICENSE). Architecture notes are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
