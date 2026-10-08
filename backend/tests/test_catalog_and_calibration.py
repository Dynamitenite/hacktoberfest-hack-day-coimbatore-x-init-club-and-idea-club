import io

import numpy as np
import pytest
from PIL import Image

import cv2

from app.catalog import (
    Catalog,
    decode_color_bands,
    load_catalog,
    normalize_board_pin,
    parse_hole,
    strip_id,
    validate_template,
)
from app.image_processing import UploadError, calibrate, decode_bgr, validate_and_normalize
from app.schemas import Point


# ---------------------------------------------------------------- catalog


def test_template_references_only_catalog_parts(template, catalog):
    validate_template(template, catalog)
    assert {template.supported_board_id, *template.component_ids} <= set(catalog.parts)


def test_template_with_unknown_part_is_rejected(template, catalog):
    bad = template.model_copy(update={"component_ids": [*template.component_ids, "mystery_ic"]})
    with pytest.raises(ValueError):
        validate_template(bad, catalog)


def test_every_catalog_fact_has_a_source_or_note(catalog):
    for part in catalog.parts.values():
        assert part.verification_note
        if part.kind in ("dev_board", "led", "resistor"):
            assert part.sources, part.id
    assert not any(p.electrical_limits for p in catalog.parts.values()), "no ratings may be stored without a source"


def test_breadboard_strip_rules(board):
    assert strip_id("a", 10, board) == strip_id("e", 10, board)
    assert strip_id("f", 10, board) == strip_id("j", 10, board)
    assert strip_id("e", 10, board) != strip_id("f", 10, board)  # centre channel
    assert strip_id("a", 10, board) != strip_id("a", 11, board)


def test_hole_parsing(board):
    assert parse_hole("C10", board) == ("c", 10)
    assert parse_hole("k10", board) is None and parse_hole("a31", board) is None and parse_hole("a0", board) is None
    assert parse_hole(None, board) is None and parse_hole("DROP TABLE", board) is None


def test_resistor_colour_code():
    assert decode_color_bands(["red", "red", "brown", "gold"]) == 220
    assert decode_color_bands(["brown", "black", "red"]) == 1000
    assert decode_color_bands(["red", "pink", "brown"]) is None
    assert decode_color_bands(["red"]) is None


def test_board_pin_normalisation(catalog):
    uno = catalog.parts["arduino_uno_r3"]
    assert normalize_board_pin("~9", uno) == "D9"
    assert normalize_board_pin("9", uno) == "D9"
    assert normalize_board_pin("gnd", uno) == "GND"
    assert normalize_board_pin("A0", uno) is None  # not in the verified catalog


# ---------------------------------------------------------------- calibration


def test_calibration_ok_on_fixture_with_correct_landmarks(fixture_photo, board):
    jpeg, meta = fixture_photo("seeded_wrong_row")
    cal = calibrate({k: Point(**v) for k, v in meta["landmarks"].items()}, decode_bgr(jpeg), board)
    assert cal.status == "ok" and cal.metrics.holes_visible_fraction > 0.9
    assert len(cal.grid) == 300


def test_calibration_flags_misaligned_landmarks(fixture_photo, board):
    jpeg, meta = fixture_photo("seeded_wrong_row")
    pts = {k: Point(x=v["x"] + 14, y=v["y"] + 11) for k, v in meta["landmarks"].items()}  # half a pitch off
    cal = calibrate(pts, decode_bgr(jpeg), board)
    assert cal.status == "low_confidence"
    assert any("misaligned" in m or "grid" in m.lower() for m in cal.messages)


def test_calibration_flags_wrong_landmark_order(fixture_photo, board):
    jpeg, meta = fixture_photo("seeded_wrong_row")
    lm = meta["landmarks"]
    swapped = {"a1": Point(**lm["a30"]), "a30": Point(**lm["a1"]), "j30": Point(**lm["j30"]), "j1": Point(**lm["j1"])}
    cal = calibrate(swapped, decode_bgr(jpeg), board)
    assert cal.status != "ok"


def test_calibration_fails_outside_image_and_degenerate(fixture_photo, board):
    jpeg, meta = fixture_photo("seeded_wrong_row")
    img = decode_bgr(jpeg)
    lm = {k: Point(**v) for k, v in meta["landmarks"].items()}
    assert calibrate({**lm, "a1": Point(x=-40, y=10)}, img, board).status == "failed"
    collapsed = {k: Point(x=100, y=100) for k in lm}
    assert calibrate(collapsed, img, board).status == "failed"
    assert calibrate({"a1": lm["a1"]}, img, board).status == "failed"


def test_calibration_on_blank_image_is_not_ok(fixture_photo, board):
    _, meta = fixture_photo("seeded_wrong_row")
    blank = np.full((960, 1280, 3), 200, np.uint8)
    cal = calibrate({k: Point(**v) for k, v in meta["landmarks"].items()}, blank, board)
    assert cal.status == "low_confidence"


# ---------------------------------------------------------------- uploads


def _img_bytes(fmt="PNG", size=(640, 480)):
    buf = io.BytesIO()
    Image.new("RGB", size, (120, 140, 160)).save(buf, format=fmt)
    return buf.getvalue()


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_supported_formats_are_accepted_and_normalised_to_jpeg(fmt):
    out = validate_and_normalize(_img_bytes(fmt), None, 10)
    assert out.jpeg_bytes[:2] == b"\xff\xd8" and (out.width, out.height) == (640, 480)


def test_rejects_wrong_declared_type():
    with pytest.raises(UploadError):
        validate_and_normalize(_img_bytes("PNG"), "image/gif", 10)


def test_rejects_non_image_bytes_even_with_image_mime():
    with pytest.raises(UploadError):
        validate_and_normalize(b"<html>not an image</html>", "image/png", 10)


def test_rejects_gif_content_with_png_label():
    buf = io.BytesIO()
    Image.new("RGB", (640, 480)).save(buf, format="GIF")
    with pytest.raises(UploadError):
        validate_and_normalize(buf.getvalue(), "image/png", 10)


def test_rejects_oversize_and_tiny_and_empty():
    with pytest.raises(UploadError, match="larger"):
        validate_and_normalize(_img_bytes("PNG", (3000, 3000)) + b"0" * 2_000_000, "image/png", 0.5)
    with pytest.raises(UploadError, match="small"):
        validate_and_normalize(_img_bytes("PNG", (100, 100)), "image/png", 10)
    with pytest.raises(UploadError):
        validate_and_normalize(b"", "image/png", 10)


def test_large_photos_are_downscaled_and_exif_stripped():
    buf = io.BytesIO()
    img = Image.new("RGB", (4000, 3000), (10, 10, 10))
    exif = Image.Exif()
    exif[0x010F] = "SecretCameraMaker"
    img.save(buf, format="JPEG", exif=exif)
    out = validate_and_normalize(buf.getvalue(), "image/jpeg", 20)
    assert max(out.width, out.height) == 2000
    assert b"SecretCameraMaker" not in out.jpeg_bytes


def test_pin_label_with_misread_tilde_still_maps_to_d9(catalog):
    uno = catalog.parts["arduino_uno_r3"]
    for label in ("9", "~9", "-9", "–9", "D9", " ~ 9 "):
        assert normalize_board_pin(label, uno) == "D9"
    assert normalize_board_pin("-", uno) is None and normalize_board_pin("A0", uno) is None
