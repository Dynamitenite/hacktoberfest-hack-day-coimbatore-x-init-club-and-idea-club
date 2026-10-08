# Verification status

Last updated 2026-10-08. This file states plainly what has and has not been executed.

## Verified (executed)

- Backend test suite: 84 tests pass (`cd backend && pytest`), including no-silent-fallback, `/api/health` (ollama, gemini, demo), synthetic labelling and arbitrary-upload tests. The Ollama provider is tested against a mocked server.
- Frontend: `npm run build` (type-check + Vite build) succeeds.
- **Real Gemma 4 runs** through the hosted Gemini API (`gemma-4-31b-it` and `gemma-4-26b-a4b-it`) on both **synthetic demo images**; results, saved responses and an honest assessment are in [GEMMA_PROOF.md](GEMMA_PROOF.md).
- **Full UI flow with real hosted Gemma 4** (26B, headless Edge): sample image → calibrate → proposals showing model name and "hosted via Gemini API" → confirm/reject → `POSSIBLE MISMATCH` for the seeded row-16 ground wire, with its image region.
- Header shows provider `gemini`, model name and "hosted via Gemini API". With the key missing it turns red, shows the setup instructions and disables Analyze, with no fallback to demo data.
- Explicit `VISION_PROVIDER=demo` flow (banner, scripted data) in the browser, on a synthetic demo image.
- Uploading an arbitrary image works end to end through the provider path (test with a mocked model).

## Not verified

- **The local Ollama path with a real model.** The `gemma4:e4b` download did not finish; Ollama is tested with a mocked server only.
- **Accuracy on real breadboard photos.** Only synthetic demo images were used; no real photos were supplied.
- **`gemma-4-31b-it` through the browser UI.** It was run through the proof script; the UI run used the 26B model because the 31B endpoint was frequently returning HTTP 500/503/504.
- The expected result for the corrected image (`MATCHES TEMPLATE` after confirmation) was verified with scripted demo data and in tests, but not with real Gemma through the UI.
- Phone layout on a device (a 390 px viewport shows no horizontal overflow).
