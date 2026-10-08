import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "tests"))

_TMP = tempfile.mkdtemp(prefix="wirewise-tests-")
os.environ["WIREWISE_DB_PATH"] = f"{_TMP}/test.db"
os.environ["WIREWISE_SAVED_DIR"] = f"{_TMP}/saved"
os.environ["GEMINI_API_KEY"] = ""  # tests never reach the network
os.environ["VISION_PROVIDER"] = "auto"

from app.catalog import load_catalog, load_templates  # noqa: E402
from app.image_processing import calibrate, decode_bgr  # noqa: E402
from app.schemas import Point  # noqa: E402


@pytest.fixture(scope="session")
def catalog():
    return load_catalog()


@pytest.fixture(scope="session")
def template():
    return load_templates()["uno_d9_led_220r"]


@pytest.fixture(scope="session")
def board(catalog):
    return catalog.breadboards["half_400"]


def fixture_dir(name: str) -> Path:
    return BACKEND / "data" / "fixtures" / name


@pytest.fixture(scope="session")
def fixture_photo():
    def load(name: str):
        jpeg = (fixture_dir(name) / "photo.jpg").read_bytes()
        meta = json.loads((fixture_dir(name) / "meta.json").read_text())
        return jpeg, meta

    return load


@pytest.fixture(scope="session")
def ok_calibration(fixture_photo, board):
    jpeg, meta = fixture_photo("seeded_wrong_row")
    pts = {k: Point(**v) for k, v in meta["landmarks"].items()}
    cal = calibrate(pts, decode_bgr(jpeg), board)
    assert cal.status == "ok"
    return cal
