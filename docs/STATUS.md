# Verification status

Last updated 2026-10-08. This file states plainly what has and has not been executed.

## Verified (executed)

- Backend test suite: all tests pass (`cd backend && pytest`), including the no-silent-fallback and `/api/health` tests. The local provider is tested against a **mocked** Ollama server.
- Frontend: `npm run build` (type-check + Vite build) succeeds.
- Browser run (Edge, headless) of the full flow in explicit `VISION_PROVIDER=demo` mode on a *synthetic* test fixture: banner, header status, calibration, scripted proposals, confirmation, `POSSIBLE MISMATCH` with its photo region and schematic link.

## Not yet verified

- **A real local Gemma 4 run.** No real Gemma response has been produced yet, so `docs/gemma_sample_response.json` does not exist and nothing here claims how good Gemma's observations are.
- **The real photos.** `fixtures/correct.jpg`, `fixtures/wrong_wire.jpg` and `fixtures/blurry.jpg` have not been supplied, so the expected outcomes (`wrong_wire.jpg` → `POSSIBLE MISMATCH`, `correct.jpg` → `MATCHES TEMPLATE`, `blurry.jpg` → `NEEDS REVIEW`) have not been checked.
- Phone layout has not been tested on a device.
