# Wirewise demo script (about two minutes)

Before starting: `.env` has `VISION_PROVIDER=gemini`, a valid `GEMINI_API_KEY` and `GEMMA_TIMEOUT_SECONDS=180`; the backend and `npm run dev` are up; and the header shows **Gemma 4 · provider gemini · model · hosted via Gemini API**. A Gemma call takes 20–60 s, and the hosted API is sometimes overloaded (HTTP 500/503/504): if so, the app says so and you press the button again. Consider `GEMINI_MODEL=gemma-4-26b-a4b-it` for faster answers, with less accurate colour-band reading. (For the local path, see the README's Ollama section.)

The demo uses the two **synthetic demo images** (computer-generated, not real photos): *ground jumper in row 16* (seeded mismatch) and *ground jumper in row 15* (corrected). Say so out loud. Anyone can also upload their own photo.

1. **Choose the circuit.** The first screen already shows the template `uno_d9_led_220r` (D9 → 220 Ω → red LED → GND).
2. **Show the target and the supported hardware.** Point at the schematic, the required connections, and the supported-hardware list with its sources.
3. **Upload the real photo.** Click the sample **Synthetic demo image: ground jumper in row 16** (or upload any image with *Choose a photo*). Mention the photo guidance and that the photo lives only in memory unless saved.
4. **Calibrate the grid.** Drag the four handles onto `a1`, `a30`, `j30`, `j1`, then click **Check the grid**. Show the grid overlay and the "grid lines up" result.
5. **Show Gemma's real proposals.** Click **Find parts and wires**. Point at the header (model and runtime) and at the "Model: gemma4:e4b · Ollama" line on a proposal. Proposals are dashed and unconfirmed.
6. **Confirm or correct them.** Confirm what is right. Correct any wrong hole position (OpenCV snapping plus your correction cover what the small model gets imprecise).
7. **Compare.** Click **Check against the template**.
8. **Show the annotated possible mismatch.** `POSSIBLE MISMATCH`: use *Show on photo* (red region) and *Show expected link* (schematic) and read the expected-vs-observed trace.
9. **Upload the corrected photo** (the **Synthetic demo image: ground jumper in row 15**) with *Start over*, repeat steps 3–7 and show the report change to `MATCHES TEMPLATE` (with the "not a safety statement" note).
10. **Say it plainly:** Gemma 4 interprets the image; deterministic graph rules perform the comparison; Wirewise never says a circuit is safe to power.

Optional: upload any blurry or unrelated photo to show `NEEDS REVIEW` or an honest failure rather than a pass. Accuracy on real breadboard photos has not been validated.

Optional failure demo: stop Ollama, click **Check again**: the app shows "Gemma 4 is unavailable" with setup steps and does not fall back to demo data.
