# Wirewise

**Check your breadboard against the circuit you meant to build.**

Wirewise compares a photo of a real low-voltage breadboard circuit with an intended circuit template. A **local Gemma 4 model** looks at the photo and *proposes* what it sees. You confirm, reject or correct each proposal. A deterministic graph comparison then reports where the confirmed wiring differs from the template, with the evidence for every finding.

It is an inspection and learning aid. It never powers, controls or talks to hardware, and it never says a circuit is safe to power.

Built for the Hacktoberfest Hack Day (Open-Source AI Hack Day, MLH): main track plus the "Best Use of Gemma 4" challenge.

- **Gemma 4 model:** `gemma4:e4b` (Gemma 4 E4B)
- **Runtime:** [Ollama](https://ollama.com), running locally on your machine
- **License:** Apache-2.0

## The problem

A wire one row off, a swapped LED, or the wrong resistor is easy to miss on a breadboard, and a photo is how makers ask for help. A language model alone can be confidently wrong about a photo. Wirewise keeps the model in the role it is good at (proposing what is visible) and puts the verdict in code that can be tested: confirmed observations in, template rules out, every finding traceable.

## What it does

1. **Choose a circuit.** One verified template ships: an Arduino UNO R3 pin D9 driving a 5 mm red LED through a 220 Ω resistor, on a half-size 400-point breadboard. You see the schematic and the expected connection list before uploading anything.
2. **Inspect your photo.** Upload a JPEG, PNG or WebP (type and size are validated). Drag four corner handles onto breadboard holes `a1`, `a30`, `j30`, `j1`. Wirewise computes a perspective correction, draws a hole grid over the photo and checks that the grid really lands on holes. If it does not, it asks you to adjust instead of guessing.
3. **Review proposals.** Gemma 4 proposes parts and wire endpoints with a bounding polygon and a confidence label. Each proposal shows its source (`gemma`, `opencv`, `user`) and the **model name and runtime** that produced it. Proposals are not facts until you confirm them. You can reject, correct hole or pin positions, or add something the model missed.
4. **Review findings.** A graph is built only from confirmed observations. NetworkX compares it with the template. The report shows one of four states: `MATCHES TEMPLATE`, `POSSIBLE MISMATCH`, `NEEDS REVIEW`, `NOT CHECKED`. Findings are grouped, each with the evidence used, the rule applied, a "Show on photo" jump to the region, and a "Show expected link" jump to the schematic.

Finding types: wrong row, wrong pin, polarity mismatch, missing connection, unexpected connection, resistor value mismatch (from colour bands you confirmed), ambiguous, and not checked.

## Setup

Requirements: Python 3.11+, Node.js 20.19+ (or 22.12+), and [Ollama](https://ollama.com/download).

### 1. Local Gemma 4 runtime (Ollama)

```bash
# Install Ollama from https://ollama.com/download, start it, then:
ollama pull gemma4:e4b        # about 9.6 GB download; E4B needs roughly 10 GB of free RAM
```

The tag `gemma4:e4b` was checked against the [Ollama library page](https://ollama.com/library/gemma4) on 2026-10-08 (other tags there: `e2b`, `12b`, `26b`, `31b`). The 26B and 31B variants need far more memory; pick a tag your machine can hold and set `OLLAMA_MODEL` accordingly. On a machine without a GPU, the first analysis loads the model and can be slow, so raise `GEMMA_TIMEOUT_SECONDS` if it times out.

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate           # Windows;  macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env        # optional: defaults already point at local Ollama
uvicorn app.main:app --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173, proxies /api to the backend
```

For a production build: `npm run build && npm run preview`. The browser only talks to the Vite server; `/api` is proxied to `BACKEND_URL` (default `http://127.0.0.1:8000`), so no key and no backend address are in browser code.

### Checking that Gemma is ready

The header of the app shows the active provider, the model name, and whether Ollama is reachable and the model is installed and loaded. The same information is at `GET /api/health`.

If Ollama is not running, the model is not installed, or a request times out, **the app shows an error with setup instructions and does not analyze anything**. It never switches to another provider or to demo data on its own.

## Providers

`VISION_PROVIDER` selects exactly one provider. There is no `auto` mode (it was removed because it silently fell back to demo data).

| Value | What it is |
| --- | --- |
| `ollama` (default) | Local Gemma 4 through Ollama. |
| `gemini` | Optional alternative: hosted Gemma 4 (`gemma-4-31b-it` or `gemma-4-26b-a4b-it`) through the Gemini API with `GEMINI_API_KEY`. The photo leaves your machine. |
| `demo` | **Tests only.** Scripted answers for the bundled synthetic demo images. No model runs. When active, the UI shows a persistent "DEMO MODE: no model is analyzing this image" banner and every observation is labelled demo data. It can only be enabled by setting `VISION_PROVIDER=demo`. |

Each analysis sends one image with a configurable timeout (`GEMMA_TIMEOUT_SECONDS`, default 60 s) and is never retried automatically.

## How Gemma 4 contributes

Gemma 4 does the part that needs vision. For the photo you give it, it:

- identifies component types: resistors, LEDs, jumper wires and the Arduino,
- reads printed labels and resistor colour bands,
- reports polarity cues (LED lead length, flat rim) where visible,
- gives coarse locations of wire ends and lead entry points,
- flags regions that are hidden or too blurry to inspect.

What Gemma 4 does **not** do:

- It never makes the pass/fail decision. The comparison is deterministic NetworkX graph logic over confirmed observations, the template and the verified catalog.
- It does not supply pixel-exact positions. OpenCV snaps its coarse coordinates to the calibrated hole grid, and you confirm or correct every proposal.
- It does not supply ratings or pinouts. Those come only from `backend/data/catalog/parts.json`, with a source per part.
- Its output is untrusted: it is validated, length-limited, and text visible in the image is never obeyed.

Every proposal records and displays the model name and runtime that produced it.

A saved real Gemma 4 response to a synthetic demo image is planned at `docs/gemma_sample_response.json`; see "Verification status" below for whether it exists yet.

## Supported hardware

| Item | Supported |
| --- | --- |
| Circuit | `uno_d9_led_220r`: D9 → 220 Ω resistor → red LED anode, LED cathode → GND |
| Board | Arduino UNO R3 (header pins D8, D9, D10, GND, 5V, 3V3 in the catalog) |
| Breadboard | Half-size 400-point, 30 rows, columns a–e and f–j, centre channel isolates |
| Parts | 220 Ω resistor (red-red-brown), 5 mm red LED, jumper wire |

Reference layout in the template: wire D9 → `a10`, R1 `c10` to `c14`, LED anode `d14` and cathode `d15`, wire `a15` → GND. Wirewise compares nets, not exact rows, so any electrically equivalent layout passes.

Only low-voltage, allowlisted circuits are supported. Mains voltage, household wiring, high-energy batteries and high-current motor circuits are out of scope, and other circuits are reported as unsupported.

## Limitations

- One circuit, one breadboard model.
- Power rails are not modelled; anything depending on them is `NOT CHECKED`.
- Wirewise only sees what is visible and confirmed. Hidden or out-of-frame wiring, damaged parts, bad contacts, voltages and currents are not checked, and catalog data could itself be wrong.
- Calibration is manual and assumes a roughly top-down photo of the whole board. Heavy glare, blur or a tilted board can fail the grid check.
- A small local model is imprecise: expect missed items and wrong hole positions, which is why every proposal needs your confirmation and OpenCV snaps positions.
- Photo guidance: whole breadboard in frame, mostly top-down, good light, no covered wires or labels.
- Tested on synthetic fixtures; accuracy on real breadboard photos has not been validated.
- `MATCHES TEMPLATE` means the visible, confirmed connections match the template. It is not a safety statement.

## Demo images and your own photos

- **Synthetic demo images** are the bundled samples. They are computer-generated renders, **not real photos**, and are labelled "Synthetic demo image" in the UI, the API and the docs. Two exist: one with a seeded wrong-row mistake (ground jumper in row 16) and a corrected one (row 15). They live in `backend/data/fixtures/` (regenerate with `python backend/scripts/generate_fixtures.py`).
- **Your own photo:** upload any JPEG, PNG or WebP on the first screen. It goes through the same calibration and Gemma 4 analysis. Accuracy on real breadboard photos has not been validated.
- If you add real photos as `fixtures/correct.jpg`, `fixtures/wrong_wire.jpg` or `fixtures/blurry.jpg`, the app lists them as additional samples.

## Verification status

See [docs/STATUS.md](docs/STATUS.md) for exactly what was run against a real Gemma 4 model and what was not.

## Tests

```bash
cd backend && pip install -r requirements-dev.txt && pytest
cd frontend && npm run build        # type-checks, then builds
```

The suite covers: proposals and rejected observations never create edges; the report never contains "safe"; provenance on every node and edge; text injected into a proposal staying inert; no API key in responses or errors; **no silent fallback** (an unreachable, missing or timed-out Gemma returns an error and never demo data); `/api/health`; upload validation including EXIF stripping; calibration failure modes; and the local provider through a mocked Ollama server (the real model is not run by the test suite).

## Dependencies

- Backend (`backend/requirements.txt`): FastAPI, Uvicorn, Pydantic, NetworkX, httpx, `opencv-python-headless`, NumPy, Pillow, python-multipart, and `google-genai` (only used for `VISION_PROVIDER=gemini`). Dev: pytest.
- Frontend (`frontend/package.json`): React 19, TypeScript, Vite, `@vitejs/plugin-react`, and the self-hosted fonts Bricolage Grotesque and Atkinson Hyperlegible Next via Fontsource.
- Runtime: Ollama and the `gemma4:e4b` model.
- Storage: SQLite (standard library) for templates and explicitly saved projects.

## Demo

A two-minute walkthrough is in [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

## Hackathon notes

Wirewise does not submit anything to MLH or OrganizerHQ; submit the repository yourself.

## License

Apache-2.0. See [LICENSE](LICENSE). Architecture notes are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
