"""Provider interface and the shared raw-proposal format.

Both the Gemma adapter and the demo provider return ``RawProposals``. The
same normalizer then turns them into ``Observation`` objects, so the demo
path exercises the real pipeline (snapping, catalog mapping, provenance).

Everything in a raw proposal is untrusted model output: it is validated,
length-limited and used only as display data or as input to deterministic
mapping. It is never executed and never fed into another prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional, Protocol

from pydantic import BaseModel, Field, field_validator

from ..schemas import CalibrationResult, CircuitTemplate, ProviderInfo
from ..catalog import Catalog

MAX_TEXT = 120
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = _CONTROL.sub("", str(value)).strip()
    return value[:MAX_TEXT] or None


class ProviderError(RuntimeError):
    """A provider failed in a way the user can act on. ``message`` is safe to show."""

    def __init__(self, message: str, *, retriable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.retriable = retriable


class RawEndpoint(BaseModel):
    point: Optional[list[float]] = Field(default=None, description="[y, x] on a 0-1000 grid")
    hole: Optional[str] = None
    board_pin: Optional[str] = None

    @field_validator("point")
    @classmethod
    def _point(cls, v):
        if v is None:
            return v
        if len(v) != 2 or any(not (-50 <= c <= 1050) for c in v):
            return None
        return [float(c) for c in v]

    @field_validator("hole", "board_pin")
    @classmethod
    def _text(cls, v):
        return clean_text(v)


class RawItem(BaseModel):
    kind: str
    box_2d: Optional[list[float]] = Field(default=None, description="[ymin, xmin, ymax, xmax] on a 0-1000 grid")
    confidence: Literal["high", "medium", "low"] = "low"
    label_text: Optional[str] = None
    color_bands: Optional[list[str]] = None
    color: Optional[str] = None
    leads: dict[str, RawEndpoint] = Field(default_factory=dict)
    orientation_note: Optional[str] = None
    description: Optional[str] = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        return (clean_text(v) or "unknown").lower()

    @field_validator("box_2d")
    @classmethod
    def _box(cls, v):
        if v is None:
            return v
        if len(v) != 4 or any(not (-50 <= c <= 1050) for c in v):
            return None
        y0, x0, y1, x1 = v
        if y1 <= y0 or x1 <= x0:
            return None
        return [float(c) for c in v]

    @field_validator("color_bands")
    @classmethod
    def _bands(cls, v):
        if v is None:
            return v
        return [clean_text(b) or "" for b in v][:6]

    @field_validator("label_text", "color", "orientation_note", "description")
    @classmethod
    def _txt(cls, v):
        return clean_text(v)


class RawObscured(BaseModel):
    box_2d: Optional[list[float]] = None
    description: Optional[str] = None

    @field_validator("description")
    @classmethod
    def _d(cls, v):
        return clean_text(v)


class RawProposals(BaseModel):
    items: list[RawItem] = Field(default_factory=list)
    obscured_regions: list[RawObscured] = Field(default_factory=list)
    notes: Optional[str] = None

    @field_validator("notes")
    @classmethod
    def _n(cls, v):
        return clean_text(v)


@dataclass
class ProposeContext:
    session_id: str
    template: CircuitTemplate
    catalog: Catalog
    image_jpeg: bytes  # original photo, never modified
    annotated_jpeg: bytes  # same photo with row/column landmarks drawn for the model
    width: int
    height: int
    calibration: CalibrationResult
    fixture_id: Optional[str] = None


class VisionProvider(Protocol):
    info: ProviderInfo

    def propose(self, ctx: ProposeContext) -> RawProposals: ...
