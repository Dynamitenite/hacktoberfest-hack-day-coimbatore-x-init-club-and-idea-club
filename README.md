# Wirewise

**Check your breadboard against the circuit you meant to build.**

Wirewise compares a photo of a low-voltage breadboard circuit with an intended circuit template. **Gemma 4** looks at the photo and *proposes* what it sees (parts, wires, resistor colour bands, rough positions). You confirm, reject or correct each proposal. A deterministic graph comparison then reports where the confirmed wiring differs from the template, with the evidence for every finding.

It is an inspection and learning aid. It never powers, controls or talks to hardware, and it never says a circuit is safe to power.

Built for Hacktoberfest Hack Day, Coimbatore 2026 (organized by INIT CLUB × iDEA CLUB with Major League Hacking): main track plus the "Best Use of Gemma 4" challenge.

- **Model (demo configuration):** Gemma 4 `gemma-4-31b-it`, hosted via the Gemini API (`VISION_PROVIDER=gemini`)
- **Also supported:** `gemma-4-26b-a4b-it` (hosted), and a local Gemma 4 through Ollama (`gemma4:e4b`, `VISION_PROVIDER=ollama`)
- **License:** Apache-2.0

## Team

> **To be filled in by the team before submission:** team name, members and each member's contributions. (Not filled in automatically, to avoid inventing information.)

## Problem statement

A wire one row off, a swapped LED polarity, or the wrong resistor is easy to miss on a breadboard, and a photo is how makers and students usually ask for help. A vision-language model alone can be confidently wrong about a photo, and "it looks right" is not a check. The target users are beginners, students and makers building small low-voltage Arduino circuits who want a second pair of eyes that shows its evidence.

Why this problem: the failure is common and cheap to make, the ground truth (a netlist) is small and exact, and that makes it a good fit for "a model proposes, code decides". *(Team: edit this paragraph if your own reason for choosing the problem differs.)*

## Solution

1. **Choose a circuit.** One verified template ships: an Arduino UNO R3 pin D9 driving a 5 mm red LED through a 220 Ω resistor, on a half-size 400-point breadboard. You see the schematic and the expected connections before uploading anything.
2. **Inspect your photo.** Upload a JPEG, PNG or WebP (type and size validated). Drag four corner handles onto the breadboard holes `a1`, `a30`, `j30`, `j1`. Wirewise computes a perspective correction, draws a hole grid and checks that it really lands on holes. If it does not, it asks you to adjust instead of guessing.
3. **Review proposals.** Gemma 4 proposes parts and wire endpoints with a confidence label. Each proposal shows its source and the **model name and runtime** that produced it. Proposals are not facts until you confirm them; you can reject, correct hole or pin positions, or add something the model missed.
4. **Review findings.** A graph is built only from confirmed observations and compared with the template. The report is one of `MATCHES TEMPLATE`, `POSSIBLE MISMATCH`, `NEEDS REVIEW`, `NOT CHECKED`. Findings are grouped, each with the evidence used, the rule applied, a "Show on photo" jump to the image region and a "Show expected link" jump to the schematic.

Finding types: wrong row, wrong pin, polarity mismatch, missing connection, unexpected connection, resistor value mismatch (from colour bands you confirmed), ambiguous, not checked.

## Innovation and differentiation

- **The model proposes, you confirm, code decides.** Gemma 4 never makes the pass/fail call. The verdict comes from NetworkX graph comparison over *confirmed* observations, template rules and a sourced parts catalog, so every finding is traceable and testable.
- **Provenance everywhere.** Every observation and graph edge records where it came from (Gemma 4 with model and runtime, OpenCV, the catalog, or you).
- **OpenCV covers what the model is weak at.** Gemma 4 gives coarse positions; OpenCV snaps them to the calibrated hole grid, and calibration refuses to continue on a grid that does not line up.
- **No silent fallback.** If the Gemma provider is unavailable, times out or has no key, the app shows an error with setup steps. It never switches to another provider or to demo data.
- **Honest wording.** It reports "the confirmed connections match this template" or "possible mismatch", keeps hidden or unconfirmed details unknown, and never calls a circuit safe.

## Technical implementation

```
Browser (React + TypeScript SPA, Vite)  --/api-->  FastAPI backend
                                                    ├─ image_processing  validate, calibrate (OpenCV), rectify
                                                    ├─ vision_provider   gemini | ollama | demo (tests) -> proposals
                                                    ├─ circuit_graph     confirmed observations -> NetworkX graph
                                                    ├─ comparison        expected vs observed -> findings
                                                    └─ storage           in-memory sessions, SQLite for saved projects
```

- **Frontend:** React 19, TypeScript, Vite (no server-side rendering), SVG overlays, plain CSS. The Vite dev server proxies `/api` to the backend so no key or backend URL is in browser code.
- **Backend:** Python, FastAPI, Pydantic schemas, OpenCV, NetworkX, SQLite.
- **Gemma 4 integration:** server-side provider adapter. One image per analysis, a configurable timeout, no automatic retries. Output is parsed leniently and treated as untrusted data (length-limited, text in the image is never obeyed).
- **Details:** see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

### How Gemma 4 contributes

Gemma 4 does the part that needs vision. For the image you give it, it:

- identifies component types: resistors, LEDs, jumper wires and the Arduino,
- reads printed labels and resistor colour bands,
- reports polarity cues (LED lead length, flat rim) where visible,
- gives coarse locations of wire ends and lead entry points,
- flags regions that are hidden or too blurry to inspect.

What Gemma 4 does **not** do: make the pass/fail decision; supply pixel-exact positions (OpenCV and you do); supply ratings or pinouts (those come only from `backend/data/catalog/parts.json`, with a source per part).

Real Gemma 4 responses to the synthetic demo images are saved in [`docs/gemma_sample_response.json`](docs/gemma_sample_response.json) (31B, corrected image) and [`docs/gemma_sample_response_26b_seeded.json`](docs/gemma_sample_response_26b_seeded.json) (26B, seeded image). [docs/GEMMA_PROOF.md](docs/GEMMA_PROOF.md) is an honest assessment: Gemma found every part and wire and the seeded row-16 mistake, but called an orange decoy disc an LED, and the 26B model misread the resistor colour bands.

## Implementation during the hackathon

This repository started from an earlier build of Wirewise (a FastAPI backend with the catalog, circuit graph, comparison, image processing, storage and tests, plus a Next.js frontend). *(Team: confirm which parts predate the Hack Day; this section describes what happened in the Hack Day working session recorded in this repository's git history.)*

Done during the working session, as recorded in the git history:

- Replaced the Next.js frontend with a React + TypeScript + Vite single-page app, porting the existing components.
- Added the local Gemma 4 provider (Ollama), kept the hosted Gemini provider, removed the silent `auto` fallback to demo data, and made the provider an explicit server-side setting.
- Added `/api/health` and a header status showing provider, model and runtime; error and "Gemma unavailable" states with setup steps.
- Recorded model name and runtime on every observation.
- Labelled the bundled images as synthetic demo images, and added tests for no-silent-fallback, health, uploads of arbitrary images and blurry images (85 backend tests in total).
- Ran real hosted Gemma 4 on the two synthetic demo images, saved real responses and wrote the assessment in [docs/GEMMA_PROOF.md](docs/GEMMA_PROOF.md).
- Wrote the demo script, status document and this README.

## Setup and usage

Requirements: Python 3.11+, Node.js 20.19+ (or 22.12+), and a Gemini API key for the hosted Gemma 4 path (or Ollama for the local path).

### 1. Configure the provider

```bash
cp .env.example .env              # then paste your key after GEMINI_API_KEY=
```

`.env.example` sets `VISION_PROVIDER=gemini`: Gemma 4 hosted via the Gemini API. Get a key at https://aistudio.google.com/apikey. The key is read only by the backend and never reaches the browser; `.env` is git-ignored. Without a key the header shows an error and the app refuses to analyze; it does not fall back to demo data.

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate           # Windows;  macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173, proxies /api to the backend
```

Production build: `npm run build && npm run preview`.

### Environment variables (see `.env.example`)

| Variable | Purpose |
| --- | --- |
| `VISION_PROVIDER` | `gemini` (hosted Gemma 4), `ollama` (local Gemma 4), or `demo` (tests only). `auto` is rejected. Server default if unset: `ollama`. |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Hosted path. Models: `gemma-4-31b-it` (default), `gemma-4-26b-a4b-it`. |
| `OLLAMA_HOST`, `OLLAMA_MODEL`, `OLLAMA_KEEP_ALIVE` | Local path. Default model `gemma4:e4b`. |
| `GEMMA_TIMEOUT_SECONDS` | Per-analysis timeout. Server default 60; `.env.example` uses 180 (hosted 31B took 56–62 s per image). |
| `MAX_UPLOAD_MB`, `SESSION_TTL_MINUTES`, `WIREWISE_DB_PATH`, `WIREWISE_SAVED_DIR`, `CORS_ORIGINS` | Uploads, sessions, storage, CORS. |

### Checking that Gemma is ready

The header shows the provider (for example `gemini`), the model name, where it runs (`hosted via Gemini API`, or the local Ollama address) and whether it is usable. The same information is at `GET /api/health`. If the key is missing or rejected, Ollama is not running, the model is not installed, or a request times out, **the app shows an error with setup instructions and analyzes nothing**. Neither `gemini` nor `ollama` ever switches to another provider or to demo data.

The hosted API is sometimes overloaded (HTTP 500/503/504 were frequent for `gemma-4-31b-it` during testing). The app reports it and you press the button again; nothing is retried automatically.

### Optional: local Gemma 4 with Ollama

```bash
# Install Ollama from https://ollama.com/download, start it, then:
ollama pull gemma4:e4b        # about 9.6 GB download; roughly 10 GB of free RAM
```

Set `VISION_PROVIDER=ollama` in `.env` (optionally `OLLAMA_MODEL`, `OLLAMA_HOST`) and restart the backend. The tag `gemma4:e4b` was checked against the [Ollama library page](https://ollama.com/library/gemma4) on 2026-10-08 (other tags: `e2b`, `12b`, `26b`, `31b`). **The local path has been tested only with a mocked Ollama server, not with a real local model.** On a machine without a GPU the first analysis loads the model and can be slow; raise `GEMMA_TIMEOUT_SECONDS` if it times out.

### Providers

| Value | What it is |
| --- | --- |
| `gemini` (set in `.env.example`) | Hosted Gemma 4 through the Gemini API. The image is sent to Google's API for the analysis. |
| `ollama` | Optional local path: Gemma 4 on your machine through Ollama. |
| `demo` | **Tests only.** Scripted answers for the bundled synthetic demo images, no model. Shows a persistent "DEMO MODE: no model is analyzing this image" banner and labels every observation as demo data. Only enabled by `VISION_PROVIDER=demo`. |

### Using the app

Follow the demo walkthrough in [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md). You can start from a bundled **synthetic demo image** or upload any JPEG, PNG or WebP (at least 320 px per side, up to `MAX_UPLOAD_MB`).

## Supported hardware

| Item | Supported |
| --- | --- |
| Circuit | `uno_d9_led_220r`: D9 → 220 Ω resistor → red LED anode, LED cathode → GND |
| Board | Arduino UNO R3 (header pins D8, D9, D10, GND, 5V, 3V3 in the catalog) |
| Breadboard | Half-size 400-point, 30 rows, columns a–e and f–j, centre channel isolates |
| Parts | 220 Ω resistor (red-red-brown), 5 mm red LED, jumper wire |

Reference layout in the template: wire D9 → `a10`, R1 `c10` to `c14`, LED anode `d14` and cathode `d15`, wire `a15` → GND. Wirewise compares nets, not exact rows, so any electrically equivalent layout passes. Only low-voltage, allowlisted circuits are supported; mains voltage, household wiring, high-energy batteries and high-current motor circuits are out of scope.

## Limitations

- Tested on synthetic fixtures; accuracy on real breadboard photos has not been validated.
- One circuit, one breadboard model. Photos of other circuits or breadboards are not supported and will not calibrate or compare meaningfully.
- Power rails are not modelled; anything depending on them is `NOT CHECKED`.
- Wirewise only sees what is visible and confirmed. Hidden or out-of-frame wiring, damaged parts, bad contacts, voltages and currents are not checked, and catalog data could itself be wrong.
- Calibration is manual and assumes a roughly top-down photo of the whole board, with the four corner holes visible. Glare, blur, low resolution or a cropped board can fail the grid check.
- Gemma 4 makes mistakes (a decoy object called an LED, misread resistor bands, run-to-run differences), which is why every proposal needs your confirmation and OpenCV snaps positions to the grid.
- `MATCHES TEMPLATE` means the visible, confirmed connections match the template. It is not a safety statement.

## Demo images

The bundled samples are **synthetic demo images**: computer-generated renders, **not real photos**, labelled as such in the UI, API and docs. Two exist: a seeded wrong-row mistake (ground jumper in row 16) and a corrected one (row 15), in `backend/data/fixtures/` (regenerate with `python backend/scripts/generate_fixtures.py`). If you add real photos as `fixtures/correct.jpg`, `fixtures/wrong_wire.jpg` or `fixtures/blurry.jpg`, the app lists them as extra samples.

## Verification

[docs/STATUS.md](docs/STATUS.md) states exactly what was run and what was not. In short: 85 backend tests pass; the frontend builds; real hosted Gemma 4 31B was run through the UI on both synthetic demo images (seeded image gives `POSSIBLE MISMATCH` on the row-16 ground wire; corrected image gives `MATCHES TEMPLATE` after the decoy LED is rejected).

```bash
cd backend && pip install -r requirements-dev.txt && pytest
cd frontend && npm run build        # type-checks, then builds
```

## Open source and AI usage

**AI models**

| Component | Role | License / terms |
| --- | --- | --- |
| Gemma 4 (`gemma-4-31b-it`, `gemma-4-26b-a4b-it`) by Google DeepMind | Reads the breadboard image and proposes components, wires, colour bands and rough positions. Never decides pass/fail. | Apache-2.0 per Google's Gemma 4 release; check the model card for current terms |
| Gemma 4 `gemma4:e4b` via [Ollama](https://ollama.com) | Optional local equivalent | Model: as above. Ollama: MIT |
| Gemini API (Google) | Hosts Gemma 4 for the default demo configuration | Google API terms |

**Libraries:** FastAPI (MIT), Uvicorn (BSD-3), Pydantic (MIT), NetworkX (BSD-3), OpenCV `opencv-python-headless` (Apache-2.0), NumPy (BSD-3), Pillow (HPND), httpx (BSD-3), python-multipart (Apache-2.0), `google-genai` (Apache-2.0), React (MIT), Vite and `@vitejs/plugin-react` (MIT), TypeScript (Apache-2.0), pytest (MIT), Fontsource packages for Bricolage Grotesque and Atkinson Hyperlegible Next (fonts under the SIL OFL). Licenses are stated from general knowledge of these projects; check each package for its current terms.

**Development tooling:** this revision was developed with the assistance of Claude Code (Anthropic), which wrote and edited code and documentation under the team's direction.

**Data:** the parts catalog (`backend/data/catalog/parts.json`) lists a source per part (for example the Arduino UNO R3 datasheet and the IEC 60062 colour code). No datasets are used. The synthetic demo images are generated by `backend/scripts/generate_fixtures.py`.

## Challenges and learnings

- **Hosted model reliability and latency.** `gemma-4-31b-it` took 56–62 s per image and was often overloaded (HTTP 500/503/504), which exceeded the 60 s default timeout. We raised the hosted timeout to 180 s, report overload clearly, and kept the "no automatic retry" rule.
- **Model errors are real.** Gemma 4 called a decoy object an LED and, in the 26B model, misread resistor bands; answers also varied between runs at temperature 0. This is the reason for the propose-confirm-compare design.
- **A silent fallback is a lie.** The earlier `auto` mode fell back to scripted data when no key was set. Making the provider explicit, and failing loudly, was the most important behaviour change.
- **Local inference is heavy.** The target machine had 15.7 GB RAM and no GPU, so a local Gemma 4 download alone was many hours; the local path is therefore documented but unverified with a real model.
- **Inputs outside the supported hardware.** A set of ten sample circuit images (LED, buttons, sensors, 7-segment, transistor) was too small (307 px wide) and showed other circuits and breadboard layouts, so Wirewise rejects or cannot calibrate them. Refusing is the intended behaviour.

## Credits and license

Gemma 4 by Google DeepMind; Ollama; the open-source libraries listed above. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the architecture notes.

Licensed under Apache-2.0. See [LICENSE](LICENSE).

Wirewise does not submit anything to MLH or OrganizerHQ; submit the repository yourself.
