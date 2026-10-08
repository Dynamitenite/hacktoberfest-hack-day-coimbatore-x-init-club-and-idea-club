# Verification status

Last updated 2026-10-08. This file states plainly what has and has not been executed.

## Verified (executed)

- Backend test suite: 82 tests pass (`cd backend && pytest`), including the no-silent-fallback, `/api/health`, synthetic-labelling and arbitrary-upload tests. The local provider is tested against a **mocked** Ollama server.
- Frontend: `npm run build` (type-check + Vite build) succeeds.
- Browser run (Edge, headless) of the full flow in explicit `VISION_PROVIDER=demo` mode on a **synthetic demo image** (computer-generated, not a real photo): banner, header status, calibration, scripted proposals, confirmation, `POSSIBLE MISMATCH` with its image region and schematic link, no console errors.
- Browser run with Ollama not running: header turns red, the "Gemma 4 is unavailable" panel shows setup steps, Analyze is disabled, nothing falls back to demo data.
- Uploading an arbitrary image works end to end through the provider path (test with a mocked model).

## Not yet verified

- **A real Gemma 4 run.** No real Gemma response has been produced, so `docs/gemma_sample_response.json` does not exist and nothing here claims how good Gemma's observations are. The hosted run needs a `GEMINI_API_KEY` (none is configured on the development machine); the local run needs `gemma4:e4b` to finish downloading in Ollama.
- Accuracy on real breadboard photos has not been validated; only synthetic demo images are bundled.
- Phone layout has not been tested on a device (a 390 px viewport shows no horizontal overflow).
