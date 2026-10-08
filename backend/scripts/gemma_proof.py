"""Run the configured Gemma 4 provider on the two SYNTHETIC demo images and score it against the known layout.

Usage (from backend/, with VISION_PROVIDER and the key/runtime configured in .env):
    python scripts/gemma_proof.py [--save docs/gemma_sample_response.json] [--image seeded_wrong_row]

It uses the real pipeline: calibrate -> annotate -> provider.propose -> normalize. One model call per image,
no retries. If the provider fails, the error is printed and nothing is substituted. The "truth" is the
layout the synthetic images were rendered from (scripted proposals run through the same normalizer).
The images are computer-generated, not real photos, so these numbers say nothing about real photos.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.catalog import load_catalog, load_templates  # noqa: E402
from app.config import settings  # noqa: E402
from app.image_processing import annotate_for_model, calibrate, decode_bgr, encode_jpeg  # noqa: E402
from app.schemas import Point  # noqa: E402
from app.vision_provider import DemoProvider, ProposeContext, ProviderError, get_provider, list_fixtures, normalize  # noqa: E402

IMAGES = ("seeded_wrong_row", "corrected")


def endpoint_tokens(obs) -> dict[str, str]:
    c = obs.candidate_part_or_endpoint
    out = {}
    for term, ep in c.endpoints.items():
        out[term] = ep.hole or (f"pin:{ep.board_pin}" if ep.board_pin else ep.kind)
    return out


def score(truth, got) -> dict:
    """Match each truth part/wire to the model item of the same kind with the most agreeing endpoints."""
    rows = []
    used: set[str] = set()
    for t in truth:
        tc = t.candidate_part_or_endpoint
        if t.observation_type not in ("component", "wire") or not tc.part_id:
            continue
        tt = endpoint_tokens(t)
        best, best_hits = None, -1
        for g in got:
            gc = g.candidate_part_or_endpoint
            if g.id in used or gc.part_id != tc.part_id:
                continue
            gt = endpoint_tokens(g)
            if tc.part_id == "jumper_wire":  # wire ends are interchangeable
                hits = len(set(tt.values()) & set(gt.values()))
            else:
                hits = sum(1 for k, v in tt.items() if gt.get(k) == v)
            if hits > best_hits:
                best, best_hits = g, hits
        if best is not None:
            used.add(best.id)
        rows.append({
            "truth": t.display_name, "truth_endpoints": tt,
            "found": best.display_name if best else None, "found_endpoints": endpoint_tokens(best) if best else None,
            "endpoints_correct": max(best_hits, 0), "endpoints_total": len(tt),
            "bands_truth": tc.color_bands, "bands_found": best.candidate_part_or_endpoint.color_bands if best else None,
        })
    extra = [g.display_name for g in got if g.id not in used and g.observation_type in ("component", "wire")]
    return {"matches": rows, "extra_items": extra}


def run_image(fid: str, provider, template, catalog) -> dict:
    meta = list_fixtures()[fid]
    jpeg = Path(meta["_photo"]).read_bytes()
    img = decode_bgr(jpeg)
    board = catalog.breadboards[template.breadboard_model_id]
    cal = calibrate({k: Point(**v) for k, v in meta["landmarks"].items()}, img, board)
    annotated = encode_jpeg(annotate_for_model(img, np.array(cal.homography), board), 90)
    ctx = ProposeContext(fid, template, catalog, jpeg, annotated, img.shape[1], img.shape[0], cal, fixture_id=fid)
    truth = normalize(DemoProvider().propose(ctx), ctx, img, "demo")

    t0 = time.time()
    raw = provider.propose(ctx)  # ProviderError propagates: no fallback
    seconds = time.time() - t0
    got = normalize(raw, ctx, img, "gemma", provider.info)
    return {
        "fixture_id": fid, "image_kind": "synthetic demo image (computer-generated, not a real photo)",
        "title": meta["title"], "seconds": round(seconds, 1), "calibration_status": cal.status,
        "raw_model_text": getattr(provider, "last_raw_text", None),
        "parsed_items": [i.model_dump() for i in raw.items], "parsed_obscured_regions": [r.model_dump() for r in raw.obscured_regions],
        "observations": [json.loads(o.model_dump_json()) for o in got],
        "score": score(truth, got),
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # display names contain arrows; the Windows console defaults to cp1252
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", choices=IMAGES, action="append", help="default: both")
    ap.add_argument("--save", help="write the full result for the FIRST image run to this JSON file")
    ap.add_argument("--save-all", help="write the results for all images to this JSON file")
    args = ap.parse_args()

    if settings.vision_provider == "demo":
        print("Refusing to run: VISION_PROVIDER=demo means no model. Set VISION_PROVIDER=gemini or ollama.")
        return 2
    template = load_templates()["uno_d9_led_220r"]
    catalog = load_catalog()
    try:
        provider = get_provider(settings)
    except ProviderError as exc:
        print(f"Gemma is unavailable ({exc.code}): {exc.message}")
        return 1
    print(f"provider={provider.info.name} model={provider.info.model} runtime={provider.info.runtime}")

    results, failures = [], []
    for fid in args.image or IMAGES:
        print(f"\n=== {fid} (synthetic demo image) ===")
        try:
            r = run_image(fid, provider, template, catalog)
        except ProviderError as exc:
            print(f"FAILED ({exc.code}): {exc.message}")
            failures.append({"fixture_id": fid, "error_code": exc.code, "error": exc.message})
            continue  # no retry, no substitute: the failure is recorded as-is
        results.append(r)
        print(f"model answered in {r['seconds']} s; {len(r['parsed_items'])} items, {len(r['parsed_obscured_regions'])} obscured regions")
        for m in r["score"]["matches"]:
            print(f"  truth {m['truth']!r}: found={m['found']!r} endpoints {m['endpoints_correct']}/{m['endpoints_total']} "
                  f"truth={m['truth_endpoints']} got={m['found_endpoints']}")
            if m["bands_truth"]:
                print(f"    colour bands truth={m['bands_truth']} got={m['bands_found']}")
        print(f"  extra items not in truth: {r['score']['extra_items']}")

    header = {
        "generated": datetime.now(timezone.utc).isoformat(), "provider": provider.info.model_dump(),
        "note": "Real response from the model named below, run on a SYNTHETIC demo image (computer-generated, not a real photo).",
    }
    if args.save and results:
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(json.dumps({**header, **results[0]}, indent=2) + "\n", encoding="utf-8")
        print(f"\nsaved {args.save}")
    if args.save_all:
        Path(args.save_all).write_text(json.dumps({**header, "results": results, "failures": failures}, indent=2) + "\n", encoding="utf-8")
        print(f"saved {args.save_all}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
