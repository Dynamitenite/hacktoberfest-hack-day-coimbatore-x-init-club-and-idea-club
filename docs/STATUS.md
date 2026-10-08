# Verification status

Last updated 2026-10-08. This file states plainly what has and has not been executed.

## Verified (executed)

- Backend test suite: 85 tests pass (`cd backend && pytest`), including no-silent-fallback, `/api/health` (ollama, gemini, demo), synthetic labelling and arbitrary-upload tests. The Ollama provider is tested against a mocked server.
- Frontend: `npm run build` (type-check + Vite build) succeeds.
- **Real Gemma 4 runs** through the hosted Gemini API (`gemma-4-31b-it` and `gemma-4-26b-a4b-it`) on both **synthetic demo images**; results, saved responses and an honest assessment are in [GEMMA_PROOF.md](GEMMA_PROOF.md).
- **Full UI flow with real hosted Gemma 4 31B** (headless Edge, `gemma-4-31b-it`), on both synthetic demo images: calibrate → proposals showing model name and "hosted via Gemini API" → confirm, reject the decoy LED → the seeded image gives `POSSIBLE MISMATCH` with exactly one finding (ground wire row 16 vs LED cathode row 15) on the right image region; the corrected image gives `MATCHES TEMPLATE`. (An earlier run with the 26B model is described in GEMMA_PROOF.md.)
- A heavily blurred synthetic image does not calibrate as `ok` (test).
- Phone layout in an emulated 390x844 touch viewport (headless Edge): no horizontal overflow on any of the five screens; corner handles are 28 px visible with a 52 px hit area and were moved by simulated touch input without the page scrolling; buttons are at least 44 px on touch screens.
- Header shows provider `gemini`, model name and "hosted via Gemini API". With the key missing it turns red, shows the setup instructions and disables Analyze, with no fallback to demo data.
- Explicit `VISION_PROVIDER=demo` flow (banner, scripted data) in the browser, on a synthetic demo image.
- Uploading an arbitrary image works end to end through the provider path (test with a mocked model).

## Not verified

- **The local Ollama path with a real model.** The `gemma4:e4b` download did not finish; Ollama is tested with a mocked server only.
- **Accuracy on real breadboard photos.** Only synthetic demo images were used; no real photos were supplied.
- Reliability of the hosted 31B endpoint: it often returned HTTP 500/503/504 during the proof runs. The UI runs above succeeded, but a demo can still hit an overload.
- The ten sample circuit images in `docs/` (a zip): not part of the supported hardware; see the README's "Challenges" and the notes given to the team. They are rejected as too small (307 px wide) and show other circuits.
- Phone layout on a real device. It was checked only in an emulated 390x844 touch viewport (headless Edge).
