"""Deterministic demo provider.

Serves recorded, Gemma-format proposals for the bundled synthetic photos so the
whole flow works with no API key and no network. It never calls a model and it
refuses photos it does not recognise rather than inventing observations.
"""

from __future__ import annotations

import json
from functools import lru_cache

import cv2
import numpy as np

from ..catalog import data_path
from ..schemas import ProviderInfo
from .base import ProposeContext, ProviderError, RawProposals

FIXTURES_DIR = data_path("fixtures")
_SIG = 48


def _signature(jpeg: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_GRAYSCALE)
    small = cv2.resize(img, (_SIG, _SIG), interpolation=cv2.INTER_AREA).astype(np.float32)
    return (small - small.mean()) / (small.std() + 1e-6)


@lru_cache(maxsize=1)
def list_fixtures() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not FIXTURES_DIR.is_dir():
        return out
    for d in sorted(FIXTURES_DIR.iterdir()):
        meta_path = d / "meta.json"
        if not meta_path.is_file():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["_photo"] = str(d / "photo.jpg")
        meta["_proposals"] = str(d / "proposals.json")
        out[meta["id"]] = meta
    return out


@lru_cache(maxsize=8)
def _fixture_signature(fixture_id: str) -> np.ndarray:
    with open(list_fixtures()[fixture_id]["_photo"], "rb") as fh:
        return _signature(fh.read())


def match_fixture(jpeg: bytes) -> str | None:
    """Recognise a bundled demo photo even after it was re-encoded by the upload path."""
    sig = _signature(jpeg)
    best, best_score = None, 0.0
    for fid in list_fixtures():
        score = float((sig * _fixture_signature(fid)).mean())  # normalised correlation
        if score > best_score:
            best, best_score = fid, score
    return best if best_score > 0.97 else None


class DemoProvider:
    def __init__(self) -> None:
        self.info = ProviderInfo(
            name="demo",
            model=None,
            integration="Scripted fixtures in Gemma's response format (no model call)",
            is_demo=True,
            detail="Demo mode: observations come from recorded fixtures for the bundled demo photos only.",
        )

    def propose(self, ctx: ProposeContext) -> RawProposals:
        fid = ctx.fixture_id or match_fixture(ctx.image_jpeg)
        if not fid or fid not in list_fixtures():
            raise ProviderError(
                "Demo mode only recognises the bundled demo photos. To analyse your own photo, "
                "set GEMINI_API_KEY on the server and choose the Gemma provider."
            )
        with open(list_fixtures()[fid]["_proposals"], encoding="utf-8") as fh:
            return RawProposals.model_validate(json.load(fh))
