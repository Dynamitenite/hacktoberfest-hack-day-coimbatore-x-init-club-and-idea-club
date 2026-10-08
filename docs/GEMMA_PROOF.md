# Gemma 4 proof run

Date: 2026-10-08. Provider: `gemini` (hosted via the Gemini API). Models: `gemma-4-31b-it` and `gemma-4-26b-a4b-it`.
Script: `backend/scripts/gemma_proof.py` (real pipeline: calibrate → annotate → model → normalize; one call per image; no retries).

**Images used: the two bundled *synthetic demo images* (computer-generated, not real photos).** Accuracy on real breadboard photos has not been validated, and these numbers say nothing about it.

"Truth" is the layout the synthetic images were rendered from. Scores count wire/lead endpoints that, after OpenCV snaps Gemma's coarse positions to the calibrated grid, land on the right hole or Arduino pin.

## Saved real responses

- [`gemma_sample_response.json`](gemma_sample_response.json): `gemma-4-31b-it` on the *corrected* synthetic demo image (56.3 s).
- [`gemma_sample_response_26b_seeded.json`](gemma_sample_response_26b_seeded.json): `gemma-4-26b-a4b-it` on the *seeded wrong-row* synthetic demo image (22.4 s).

Each file holds the raw model text, the parsed items, the normalized observations (with model name and runtime) and the score.

## Results

| Run | Model | Time | Parts and wires found | Endpoints correct | Other |
| --- | --- | --- | --- | --- | --- |
| Seeded (saved only in the console log, not as a file) | 31B | 57.6 s | all 4 (2 wires, resistor, LED) | 8/8, including the seeded ground wire in row 16 | 1 extra "LED" |
| Corrected (saved) | 31B | 56.3 s | all 4 | 8/8, ground wire in row 15 | 1 extra "LED" (see below) |
| Seeded (saved) | 26B A4B | 22.4 s | all 4 | 8/8 | resistor bands misread; 1 extra "LED"; 1 unrecognised object |

## What Gemma 4 was good at

- Identifying the resistor, LED, both jumper wires and the Arduino.
- Coarse positions that OpenCV could snap to the right holes (the pin-9 and GND wire ends, the resistor and LED legs). The seeded row-16 ground wire was located correctly, so the deterministic comparison can flag it.
- 31B read the colour bands correctly (red, red, brown, gold) on both images.
- It followed the JSON format; nothing had to be repaired.

## Where it was weak (observed, not guessed)

- **The orange decoy disc beside the breadboard was called an LED, with "high" confidence** (31B on the corrected image). It would appear as a second LED proposal; the user must reject it. The deterministic pipeline never trusts it unconfirmed.
- **26B misread the resistor bands** (brown-black-orange, i.e. 10 kΩ, in the saved run; "1 kΩ" in a later browser run). If the user confirms that, the report shows a value mismatch. The bands need the user's check.
- **Not repeatable at temperature 0.** The same 26B request returned "D9" in one run and a pin label of "-9" in another. A dash-for-tilde misreading is now accepted by the pin-label normalizer (test added), but expect run-to-run differences.
- **No LED polarity cue was reported** by 31B, so the app keeps that proposal at low confidence and needs the user to confirm polarity.
- Exact endpoint positions are only coarse; OpenCV snapping and the user's confirmation are what make them usable, as designed.

## Hosted-API reliability and timeouts

- `gemma-4-31b-it` answers in about 56–62 s. With the 60 s default the request hits its deadline (HTTP 504), so the hosted setup uses `GEMMA_TIMEOUT_SECONDS=180` in `.env.example`.
- The hosted 31B model was often overloaded during this run: most attempts on the seeded image returned HTTP 500/503/504, while others succeeded. These are errors on Google's side (identical requests with different options sometimes worked). The app reports them ("temporarily overloaded… Nothing was analyzed"), does not retry, and does not fall back to demo data. Pressing the button again is the user's choice.
- `gemma-4-26b-a4b-it` was more reliable and faster here but made the errors listed above.

## End-to-end run through the UI (26B, synthetic demo image, headless Edge)

Upload sample → check grid → Gemma proposals (each shows `gemma-4-26b-a4b-it · hosted via Gemini API`) → confirm/reject → compare. Result: `POSSIBLE MISMATCH` with the seeded finding **"LED1 cathode in row 15, Arduino GND in row 16 (adjacent row)"**, highlighted on the right image region. The report also contained two extra findings caused by Gemma's errors that the reviewer confirmed without correcting (the misread resistor value and the "-9" pin label), which is what the confirmation step exists to catch.
