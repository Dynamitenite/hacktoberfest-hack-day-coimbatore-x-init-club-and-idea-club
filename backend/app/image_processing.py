"""Upload validation, manual-landmark calibration and perspective correction.

All geometry here is deterministic OpenCV/NumPy. Gemma is never asked to
locate the grid; the user places four landmark holes and we derive the
homography from them, then sanity-check it against the photo.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from .catalog import all_holes, canonical_hole_position
from .schemas import (
    BreadboardModel,
    CalibrationMetrics,
    CalibrationResult,
    GridHole,
    Point,
)

ALLOWED_MIME = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
MAX_PIXELS = 40_000_000
MIN_SIDE = 320
MAX_ANALYSIS_SIDE = 2000  # stored/analysed image is downscaled to this longest side


class UploadError(ValueError):
    """Raised with a user-presentable message when an upload is rejected."""


@dataclass
class ValidatedImage:
    jpeg_bytes: bytes
    width: int
    height: int
    original_format: str


def validate_and_normalize(data: bytes, declared_mime: str | None, max_mb: float) -> ValidatedImage:
    if not data:
        raise UploadError("The file is empty.")
    if len(data) > max_mb * 1024 * 1024:
        raise UploadError(f"The image is larger than {max_mb:g} MB. Resize or compress it and try again.")
    if declared_mime and declared_mime.lower() not in ALLOWED_MIME:
        raise UploadError("Unsupported file type. Use a JPEG, PNG or WebP image.")
    try:
        probe = Image.open(io.BytesIO(data))
        probe.verify()  # cheap integrity check
        img = Image.open(io.BytesIO(data))  # verify() invalidates the handle
        fmt = (img.format or "").upper()
        if fmt not in ALLOWED_MIME.values():
            raise UploadError("Unsupported image content. Use a JPEG, PNG or WebP image.")
        if img.width * img.height > MAX_PIXELS:
            raise UploadError("The image has too many pixels. Use a photo under 40 megapixels.")
        img = _apply_exif_orientation(img).convert("RGB")
    except UploadError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise UploadError("The file could not be read as a valid image.") from exc

    if min(img.size) < MIN_SIDE:
        raise UploadError(f"The image is too small. Each side should be at least {MIN_SIDE}px.")

    longest = max(img.size)
    if longest > MAX_ANALYSIS_SIDE:
        scale = MAX_ANALYSIS_SIDE / longest
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)  # re-encoding also strips EXIF/metadata
    return ValidatedImage(buf.getvalue(), img.width, img.height, fmt)


def _apply_exif_orientation(img: Image.Image) -> Image.Image:
    from PIL import ImageOps

    return ImageOps.exif_transpose(img)


def decode_bgr(jpeg_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise UploadError("Stored image could not be decoded.")
    return img


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

LANDMARKS = ["a1", "a30", "j30", "j1"]


def _landmark_canonical(board: BreadboardModel) -> dict[str, tuple[float, float]]:
    out = {}
    for name in LANDMARKS:
        col, row = name[0], int(name[1:])
        out[name] = canonical_hole_position(col, row, board)
    return out


def compute_homography(points: dict[str, Point], board: BreadboardModel) -> np.ndarray:
    canon = _landmark_canonical(board)
    src = np.array([canon[n] for n in LANDMARKS], dtype=np.float32)
    dst = np.array([[points[n].x, points[n].y] for n in LANDMARKS], dtype=np.float32)
    return cv2.getPerspectiveTransform(src, dst)  # canonical pitch units -> image px


def project(H: np.ndarray, x: float, y: float) -> tuple[float, float]:
    v = H @ np.array([x, y, 1.0])
    return float(v[0] / v[2]), float(v[1] / v[2])


def invert_project(H: np.ndarray, px: float, py: float) -> tuple[float, float]:
    inv = np.linalg.inv(H)
    v = inv @ np.array([px, py, 1.0])
    return float(v[0] / v[2]), float(v[1] / v[2])


def nearest_hole(H: np.ndarray, px: float, py: float, board: BreadboardModel) -> tuple[str, float]:
    """Return (hole name, distance in pitch units) closest to an image point."""
    cx, cy = invert_project(H, px, py)
    best, best_d = "", 1e9
    for col, row in all_holes(board):
        hx, hy = canonical_hole_position(col, row, board)
        d = float(np.hypot(hx - cx, hy - cy))
        if d < best_d:
            best, best_d = f"{col}{row}", d
    return best, best_d


def _polygon_area(pts: list[tuple[float, float]]) -> float:
    x = np.array([p[0] for p in pts])
    y = np.array([p[1] for p in pts])
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _is_convex_ordered(pts: list[tuple[float, float]]) -> bool:
    signs = []
    n = len(pts)
    for i in range(n):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % n]
        cx, cy = pts[(i + 2) % n]
        cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
        signs.append(cross > 0)
    return all(signs) or not any(signs)


def _hole_contrast_score(gray: np.ndarray, x: float, y: float, r: float) -> float | None:
    """Local contrast of a candidate hole: dark centre vs lighter ring. None if outside the image."""
    h, w = gray.shape
    ri = max(2, int(round(r)))
    ro = int(round(r * 2.2))
    if not (ro + 1 <= x < w - ro - 1 and ro + 1 <= y < h - ro - 1):
        return None
    xi, yi = int(round(x)), int(round(y))
    patch = gray[yi - ro : yi + ro + 1, xi - ro : xi + ro + 1].astype(np.float32)
    yy, xx = np.mgrid[-ro : ro + 1, -ro : ro + 1]
    dist = np.hypot(xx, yy)
    inner = patch[dist <= ri * 0.8]
    ring = patch[(dist >= ri * 1.5) & (dist <= ro)]
    if inner.size == 0 or ring.size == 0:
        return None
    return float(ring.mean() - inner.mean())


def calibrate(
    points: dict[str, Point],
    image_bgr: np.ndarray,
    board: BreadboardModel,
) -> CalibrationResult:
    """Validate user landmarks and derive the pixel<->grid homography.

    Returns ``failed`` for geometrically impossible input, ``low_confidence``
    when the grid does not line up with visible holes, ``ok`` otherwise.
    A low-confidence result must be adjusted or explicitly accepted by the
    user; it is never silently treated as success.
    """
    h, w = image_bgr.shape[:2]
    messages: list[str] = []

    missing = [n for n in LANDMARKS if n not in points]
    if missing:
        return CalibrationResult(status="failed", messages=[f"Missing landmarks: {', '.join(missing)}."])

    for name in LANDMARKS:
        p = points[name]
        if not (0 <= p.x <= w and 0 <= p.y <= h):
            return CalibrationResult(
                status="failed",
                messages=[f"Landmark {name} lies outside the photo. Drag it onto the matching hole."],
            )

    poly = [(points[n].x, points[n].y) for n in LANDMARKS]
    if not _is_convex_ordered(poly) or abs(_polygon_area(poly)) < 0.02 * w * h:
        return CalibrationResult(
            status="failed",
            messages=[
                "The four landmarks do not form a sensible quadrilateral. "
                "Check that a1, a30, j30 and j1 are each on the correct corner hole."
            ],
        )

    H = compute_homography(points, board)
    canon_rows = board.rows - 1
    canon_cols = board.column_offsets_pitch[board.columns[-1]]

    # --- geometric sanity ---------------------------------------------------
    def d(p, q):
        return float(np.hypot(p[0] - q[0], p[1] - q[1]))

    a1, a30, j30, j1 = poly
    long_side_1, long_side_2 = d(a1, a30), d(j1, j30)
    short_side_1, short_side_2 = d(a1, j1), d(a30, j30)
    pitch_along = np.mean([long_side_1, long_side_2]) / canon_rows
    pitch_across = np.mean([short_side_1, short_side_2]) / canon_cols
    opposite_ratio = max(
        max(long_side_1, long_side_2) / max(min(long_side_1, long_side_2), 1e-6),
        max(short_side_1, short_side_2) / max(min(short_side_1, short_side_2), 1e-6),
    )
    axis_ratio = max(pitch_along, pitch_across) / max(min(pitch_along, pitch_across), 1e-6)
    pitch_px = float(min(pitch_along, pitch_across))

    if pitch_px < 4.0:
        messages.append(
            f"The grid pitch is only {pitch_px:.1f}px per hole. Use a closer, higher-resolution photo."
        )
    if opposite_ratio > 1.6:
        messages.append(
            "Opposite sides of the breadboard differ strongly in length. The photo is taken at a steep angle or a landmark is misplaced."
        )
    if axis_ratio > 1.6:
        messages.append(
            "Row spacing and column spacing disagree. Check that the corners are on a1, a30, j30 and j1."
        )

    # --- do the predicted holes land on visible holes? -------------------------
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    radius = max(2.0, pitch_px * 0.18)
    scores: list[float] = []
    for col, row in all_holes(board):
        cx, cy = canonical_hole_position(col, row, board)
        px, py = project(H, cx, cy)
        s = _hole_contrast_score(gray, px, py, radius)
        if s is not None:
            scores.append(s)
    phantom_scores: list[float] = []
    # Phantom grid shifted half a pitch: should NOT line up with holes if the real grid does.
    for col, row in all_holes(board):
        cx, cy = canonical_hole_position(col, row, board)
        px, py = project(H, cx + 0.5, cy + 0.5)
        s = _hole_contrast_score(gray, px, py, radius)
        if s is not None:
            phantom_scores.append(s)

    threshold = 6.0
    visible_fraction = float(np.mean([s > threshold for s in scores])) if scores else 0.0
    phantom_fraction = float(np.mean([s > threshold for s in phantom_scores])) if phantom_scores else None
    median_offset = None  # reserved: sub-pitch drift estimate

    metrics = CalibrationMetrics(
        pitch_px_min=round(pitch_px, 2),
        opposite_side_ratio=round(float(opposite_ratio), 3),
        axis_pitch_ratio=round(float(axis_ratio), 3),
        holes_checked=len(scores),
        holes_visible_fraction=round(visible_fraction, 3),
        median_offset_pitch=median_offset,
        phantom_visible_fraction=round(phantom_fraction, 3) if phantom_fraction is not None else None,
    )

    grid_ok = (
        len(scores) >= 0.8 * len(all_holes(board))
        and visible_fraction >= 0.55
        and (phantom_fraction is None or visible_fraction - phantom_fraction >= 0.25)
    )
    if len(scores) < 0.8 * len(all_holes(board)):
        messages.append("Part of the predicted grid falls outside the photo. Keep the whole breadboard in frame.")
    elif not grid_ok:
        messages.append(
            f"Only {visible_fraction:.0%} of the predicted grid positions look like holes, "
            "so the grid may be misaligned. Nudge the four landmarks and re-check the overlay."
        )

    geometry_ok = not any(
        m.startswith(("The grid pitch", "Opposite sides", "Row spacing")) for m in messages
    )
    status = "ok" if (geometry_ok and grid_ok) else "low_confidence"
    if status == "ok":
        messages.append("Grid lines up with visible holes. Check the overlay before continuing.")

    grid = []
    for col, row in all_holes(board):
        cx, cy = canonical_hole_position(col, row, board)
        px, py = project(H, cx, cy)
        grid.append(GridHole(hole=f"{col}{row}", x=round(px, 2), y=round(py, 2)))

    return CalibrationResult(
        status=status,
        messages=messages,
        metrics=metrics,
        homography=H.tolist(),
        grid=grid,
        rectified_available=True,
    )


def rectify(image_bgr: np.ndarray, H: np.ndarray, board: BreadboardModel, px_per_pitch: int = 28, margin_pitch: float = 2.0) -> np.ndarray:
    """Warp the photo so holes sit on an axis-aligned grid (rows horizontal)."""
    canon_rows = board.rows - 1
    canon_cols = board.column_offsets_pitch[board.columns[-1]]
    width = int(round((canon_rows + 2 * margin_pitch) * px_per_pitch))
    height = int(round((canon_cols + 2 * margin_pitch) * px_per_pitch))
    # canonical -> rectified
    S = np.array(
        [[px_per_pitch, 0, margin_pitch * px_per_pitch], [0, px_per_pitch, margin_pitch * px_per_pitch], [0, 0, 1]],
        dtype=np.float64,
    )
    M = S @ np.linalg.inv(H)  # image px -> canonical -> rectified px
    return cv2.warpPerspective(image_bgr, M, (width, height), flags=cv2.INTER_AREA)


def encode_jpeg(image_bgr: np.ndarray, quality: int = 90) -> bytes:
    ok, buf = cv2.imencode(".jpg", image_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return buf.tobytes()


# ---------------------------------------------------------------------------
# Suggested landmarks (deterministic helper, user must still verify)
# ---------------------------------------------------------------------------


def suggest_landmarks(image_bgr: np.ndarray) -> dict[str, Point] | None:
    """Best-effort guess of the breadboard's four corner holes from the largest
    light rectangular blob. It only pre-positions the draggable handles; the
    user always confirms or adjusts them."""
    h, w = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    for mask in (th, 255 - th):
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(contours, key=cv2.contourArea, reverse=True)[:3]:
            if cv2.contourArea(c) < 0.12 * w * h:
                continue
            rect = cv2.minAreaRect(c)
            box = cv2.boxPoints(rect)
            if cv2.contourArea(box) > 0.97 * w * h:
                continue
            # order: long axis = rows. Return top-left/bottom-left/bottom-right/top-right style ordering.
            pts = sorted(box.tolist(), key=lambda p: (p[0], p[1]))
            left = sorted(pts[:2], key=lambda p: p[1])
            right = sorted(pts[2:], key=lambda p: p[1])
            tl, bl, tr, br = left[0], left[1], right[0], right[1]
            return {
                "a1": Point(x=tl[0], y=tl[1]),
                "a30": Point(x=tr[0], y=tr[1]),
                "j30": Point(x=br[0], y=br[1]),
                "j1": Point(x=bl[0], y=bl[1]),
            }
    return None


# ---------------------------------------------------------------------------
# Helper image for the vision model
# ---------------------------------------------------------------------------


def annotate_for_model(image_bgr: np.ndarray, H: np.ndarray, board: BreadboardModel) -> np.ndarray:
    """Draw row numbers and column letters just outside the calibrated grid.

    The marks are drawn on a copy, in the margin around the breadboard, so the
    model can read hole coordinates without the overlay hiding any hardware.
    """
    out = image_bgr.copy()
    pitch = float(np.linalg.norm(np.array(project(H, 1, 0)) - np.array(project(H, 0, 0))))
    scale = float(np.clip(pitch / 30.0, 0.45, 1.2))
    font = cv2.FONT_HERSHEY_SIMPLEX

    def label(text: str, cx: float, cy: float) -> None:
        (tw, th), _ = cv2.getTextSize(text, font, scale, 2)
        org = (int(cx - tw / 2), int(cy + th / 2))
        cv2.putText(out, text, org, font, scale, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(out, text, org, font, scale, (0, 255, 255), 2, cv2.LINE_AA)

    far = board.column_offsets_pitch[board.columns[-1]]
    for row in (1, 5, 10, 15, 20, 25, 30):
        label(str(row), *project(H, row - 1, -1.6))
        label(str(row), *project(H, row - 1, far + 1.6))
    for col in board.columns:
        label(col, *project(H, -1.7, board.column_offsets_pitch[col]))
    return out
