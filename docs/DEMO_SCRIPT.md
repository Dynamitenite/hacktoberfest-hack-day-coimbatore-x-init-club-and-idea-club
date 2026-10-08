# Wirewise demo script

Plan for about **3 minutes**. A real Gemma 4 call takes 20–60 s (31B: 56–62 s, 26B A4B: about 22 s), and the demo makes two, so a strict two-minute version is only possible if you analyze the second image before you start (see "Timing").

**Say this up front:** the two demo images are **synthetic demo images** (computer-generated, not real photos). Accuracy on real breadboard photos has not been validated.

## Before you start (once)

1. `.env` has `VISION_PROVIDER=gemini`, a valid `GEMINI_API_KEY` and `GEMMA_TIMEOUT_SECONDS=180`.
2. Backend: `cd backend && uvicorn app.main:app --port 8000`. Frontend: `cd frontend && npm run dev`. Open http://localhost:5173.
3. Check the header: **Gemma 4 · provider gemini · gemma-4-31b-it · hosted via Gemini API · Model loaded**. A red header means the key is missing or wrong: fix `.env` and restart the backend. (Demo mode, `VISION_PROVIDER=demo`, shows a yellow DEMO MODE banner and uses no model; do not present it as a Gemma run.)
4. Do one throwaway run of the whole flow to warm up and to learn whether the hosted API is overloaded right now.

## Walkthrough

1. **Choose the circuit.** The first screen shows the template `UNO R3 → 220 Ω → red LED on D9`. Point at the schematic and "Connections the template requires". *Say:* "Wirewise checks one verified circuit; anything else it refuses rather than guesses."
2. **Show the supported hardware.** Scroll to "Supported hardware": each part lists its terminals and a source. *Say:* "Pinouts come from this catalog, never from the model."
3. **Load the seeded image.** In "Or try a sample image" click **Synthetic demo image: ground jumper in row 16**. Mention the badge: it is synthetic. (To show arbitrary input, use **Choose a photo** with any JPEG, PNG or WebP of at least 320 px per side; a photo of another circuit will not calibrate.)
4. **Calibrate.** Show the four corner handles (`a1`, `a30`, `j30`, `j1`), pre-placed here; on your own photo you drag them onto the corner holes. Click **Check the grid** and show "✓ Grid lines up" with "Holes matched 99%". *Say:* "If the grid didn't land on real holes it would stop and ask me to adjust."
5. **Gemma's real proposals.** Click **Find parts and wires** and wait (see "Timing"). Point at the header and at a proposal's line "Model: gemma-4-31b-it · hosted via Gemini API". Proposals are dashed: **proposed, not facts**. Expect the resistor, the LED, the two wires, and an extra "LED" for the orange disc beside the breadboard (a real Gemma mistake, see [GEMMA_PROOF.md](GEMMA_PROOF.md)).
6. **Confirm or correct.** Click **Confirm** on the resistor, LED, green wire and black wire. **Reject** the extra LED. *Say:* "The model's mistake is caught here, not silently accepted."
7. **Compare.** Click **Check against the template**.
8. **Show the possible mismatch.** Result: `POSSIBLE MISMATCH`, one finding: "Wire or lead on the wrong row: LED1 cathode ↔ Arduino GND". Click **Show on photo** (red region) and **Show expected link** (schematic), and read the twin trace: LED cathode in row 15, ground wire in row 16.
9. **Corrected image.** Click **Start over with another photo**, load **Synthetic demo image: ground jumper in row 15**, and repeat steps 4–7 (reject the extra LED again). Result: `MATCHES TEMPLATE`, with the note that this is not a safety statement.
10. **Say it plainly:** "Gemma 4 interprets the image; deterministic graph rules make the comparison; Wirewise never says a circuit is safe to power."

## Timing

- **Live (recommended):** use `gemma-4-31b-it`, and fill the 30–60 s wait by explaining the architecture (model proposes, you confirm, code decides). Total about 3 minutes.
- **Faster:** set `GEMINI_MODEL=gemma-4-26b-a4b-it` (about 22 s). In testing it misread the resistor colour bands (as 10 kΩ and as 1 kΩ). If that happens, use **Correct…** on the resistor to fix it: a good live demonstration of the confirm/correct step, but it adds time.
- **Strict 2 minutes:** analyze the corrected image in a second browser tab before you present, and switch to it for step 9.

## If something goes wrong

- **"The Gemini API is temporarily overloaded…" (HTTP 500/503/504):** the hosted API is busy. Nothing was analyzed and nothing is retried automatically. Press **Find parts and wires** again. This happened often with 31B during testing.
- **Header red / "Gemma 4 is unavailable":** the key is missing or invalid. The app does not switch to demo data, which is itself worth showing.
- **Last resort:** show the saved real responses in `docs/gemma_sample_response.json` and `docs/gemma_sample_response_26b_seeded.json`, and say they are saved outputs, not a live run.

## On a phone

- Open the app on the same network (`npm run dev -- --host`, then use the laptop's address), or use a browser's device mode at 390 px width.
- **Take a photo** opens the camera. Keep the whole board in frame, top-down, with good light.
- The four corner handles are large touch targets (about 52 px); drag them onto the corner holes. The page does not scroll while you drag a handle.
- Buttons are at least 44 px high on touch screens.

## Optional extras

- **Unsupported image:** upload any photo of a different circuit or a tiny image: it is rejected or fails the grid check instead of producing a false result (images under 320 px per side are rejected outright).
- **Failure state:** blank `GEMINI_API_KEY` in `.env` and restart the backend: the header turns red, the app shows "Gemma 4 is unavailable" with setup steps and does not fall back to demo data.
- **Local model:** see the README's Ollama section. It has been tested only with a mocked server, not with a real local model.
