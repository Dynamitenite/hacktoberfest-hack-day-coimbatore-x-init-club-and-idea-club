"""Local component catalog, breadboard model and circuit templates.

The catalog is the only source of electrical facts in Wirewise. Nothing
here is ever filled in from a model's general knowledge: if a fact is not
stored in ``data/catalog/parts.json`` or a template file, it is not checked.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .config import DATA_DIR
from .schemas import BreadboardModel, CircuitTemplate, PartCatalogItem

CATALOG_PATH = DATA_DIR / "catalog" / "parts.json"
TEMPLATES_DIR = DATA_DIR / "templates"

HOLE_RE = re.compile(r"^([a-jA-J])\s*-?\s*(\d{1,2})$")

# IEC 60062 colour code: digit values and multipliers.
COLOR_DIGITS = {
    "black": 0, "brown": 1, "red": 2, "orange": 3, "yellow": 4,
    "green": 5, "blue": 6, "violet": 7, "purple": 7, "grey": 8, "gray": 8, "white": 9,
}
COLOR_MULTIPLIERS = {**{k: 10**v for k, v in COLOR_DIGITS.items()}, "gold": 0.1, "silver": 0.01}


class Catalog:
    def __init__(self, raw: dict) -> None:
        self.version: str = raw["catalog_version"]
        self.parts: dict[str, PartCatalogItem] = {
            p["id"]: PartCatalogItem.model_validate(p) for p in raw["parts"]
        }
        self.breadboards: dict[str, BreadboardModel] = {
            b["id"]: BreadboardModel.model_validate(b) for b in raw["breadboards"]
        }

    def part(self, part_id: str | None) -> PartCatalogItem | None:
        return self.parts.get(part_id) if part_id else None


@lru_cache(maxsize=1)
def load_catalog() -> Catalog:
    return Catalog(json.loads(CATALOG_PATH.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def load_templates() -> dict[str, CircuitTemplate]:
    catalog = load_catalog()
    templates: dict[str, CircuitTemplate] = {}
    for path in sorted(TEMPLATES_DIR.glob("*.json")):
        tpl = CircuitTemplate.model_validate(json.loads(path.read_text(encoding="utf-8")))
        validate_template(tpl, catalog)
        templates[tpl.id] = tpl
    return templates


def validate_template(tpl: CircuitTemplate, catalog: Catalog) -> None:
    """Refuse to load a template that references anything not in the catalog."""
    if tpl.breadboard_model_id not in catalog.breadboards:
        raise ValueError(f"Template {tpl.id}: unknown breadboard {tpl.breadboard_model_id}")
    for pid in [tpl.supported_board_id, *tpl.component_ids]:
        if pid not in catalog.parts:
            raise ValueError(f"Template {tpl.id}: part {pid} is not in the catalog")
    refs = {i.ref: i for i in tpl.instances}
    node_ids = set()
    for node in tpl.expected_nodes:
        inst = refs.get(node.instance)
        if inst is None:
            raise ValueError(f"Template {tpl.id}: node {node.id} uses unknown instance")
        part = catalog.parts[inst.part_id]
        if node.terminal not in part.terminal_names:
            raise ValueError(f"Template {tpl.id}: {node.terminal} is not a catalog terminal of {part.id}")
        if node.id != f"{node.instance}.{node.terminal}":
            raise ValueError(f"Template {tpl.id}: node id {node.id} must be '<instance>.<terminal>'")
        node_ids.add(node.id)
    rule_ids = {r.id for r in tpl.explicit_rules}
    for edge in tpl.expected_edges:
        if edge.a not in node_ids or edge.b not in node_ids:
            raise ValueError(f"Template {tpl.id}: edge {edge.id} references unknown node")
        if edge.rule_id not in rule_ids:
            raise ValueError(f"Template {tpl.id}: edge {edge.id} references unknown rule")


# ---------------------------------------------------------------------------
# Breadboard helpers (pure, deterministic)
# ---------------------------------------------------------------------------


def parse_hole(text: str | None, board: BreadboardModel) -> tuple[str, int] | None:
    if not text:
        return None
    m = HOLE_RE.match(text.strip())
    if not m:
        return None
    col, row = m.group(1).lower(), int(m.group(2))
    if col not in board.columns or not (1 <= row <= board.rows):
        return None
    return col, row


def hole_name(col: str, row: int) -> str:
    return f"{col}{row}"


def strip_id(col: str, row: int, board: BreadboardModel) -> str:
    """Breadboard connectivity rule: which strip does this hole belong to."""
    for rule in board.connectivity_rules:
        if col in rule.get("columns", []):
            side = "L" if rule["id"] == "strip_left" else "R"
            return f"strip:{row}{side}"
    raise ValueError(f"Column {col} has no connectivity rule")


def strip_rule_id(col: str, board: BreadboardModel) -> str:
    for rule in board.connectivity_rules:
        if col in rule.get("columns", []):
            return rule["id"]
    raise ValueError(col)


def strip_label(strip: str) -> str:
    # strip:10L -> "row 10 (a–e)"
    body = strip.split(":", 1)[1]
    row, side = body[:-1], body[-1]
    return f"row {row} ({'a–e' if side == 'L' else 'f–j'})"


def canonical_hole_position(col: str, row: int, board: BreadboardModel) -> tuple[float, float]:
    """Hole position in pitch units: x along rows (row 1 -> 0), y across columns (a -> 0)."""
    return float(row - 1), float(board.column_offsets_pitch[col])


def all_holes(board: BreadboardModel) -> list[tuple[str, int]]:
    return [(c, r) for r in range(1, board.rows + 1) for c in board.columns]


def decode_color_bands(bands: list[str] | None) -> float | None:
    """Deterministic IEC 60062 decode of a 4-band resistor (digit, digit, multiplier[, tolerance])."""
    if not bands or len(bands) < 3:
        return None
    norm = [b.strip().lower() for b in bands]
    if norm[0] not in COLOR_DIGITS or norm[1] not in COLOR_DIGITS or norm[2] not in COLOR_MULTIPLIERS:
        return None
    value = (COLOR_DIGITS[norm[0]] * 10 + COLOR_DIGITS[norm[1]]) * COLOR_MULTIPLIERS[norm[2]]
    return round(value, 3)


def format_ohms(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value >= 1_000_000:
        return f"{value / 1_000_000:g} MΩ"
    if value >= 1000:
        return f"{value / 1000:g} kΩ"
    return f"{value:g} Ω"


def normalize_board_pin(label: str | None, part: PartCatalogItem) -> str | None:
    """Map a pin label read from silkscreen to a catalog terminal name, or None."""
    if not label:
        return None
    text = label.strip().upper().replace(" ", "")
    text = text.lstrip("~-–—_")  # the PWM tilde printed before 9 is often read as a dash
    names = {t.name.upper(): t.name for t in part.terminals}
    if text in names:
        return names[text]
    if text.isdigit() and f"D{text}" in names:
        return names[f"D{text}"]
    if text.startswith("PIN") and text[3:].isdigit() and f"D{text[3:]}" in names:
        return names[f"D{text[3:]}"]
    aliases = {"3.3V": "3V3", "3V3": "3V3", "GROUND": "GND"}
    if text in aliases and aliases[text] in part.terminal_names:
        return aliases[text]
    return None


def catalog_payload() -> dict:
    cat = load_catalog()
    return {
        "catalog_version": cat.version,
        "parts": [p.model_dump() for p in cat.parts.values()],
        "breadboards": [b.model_dump() for b in cat.breadboards.values()],
    }


def template_payload(tpl: CircuitTemplate) -> dict:
    cat = load_catalog()
    parts = {pid: cat.parts[pid].model_dump() for pid in {tpl.supported_board_id, *tpl.component_ids}}
    return {
        "template": tpl.model_dump(),
        "parts": parts,
        "breadboard": cat.breadboards[tpl.breadboard_model_id].model_dump(),
    }


def data_path(*parts: str) -> Path:
    return DATA_DIR.joinpath(*parts)
