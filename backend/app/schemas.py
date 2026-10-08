"""Typed data structures shared across Wirewise.

Every object that crosses a module boundary or the HTTP API is a Pydantic
model defined here, so the frontend, the vision providers and the graph
logic all agree on one vocabulary.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared literals
# ---------------------------------------------------------------------------

ConfidenceLabel = Literal["high", "medium", "low", "uncertain"]
# "demo" marks scripted fixture output from the demo provider; it is never presented as a Gemma result.
ObservationSource = Literal["gemma", "opencv", "user", "demo"]
ObservationStatus = Literal["proposed", "confirmed", "rejected", "corrected"]
ObservationType = Literal["board", "component", "wire", "label_text", "obscured_region"]
EvidenceSource = Literal["gemma", "opencv", "catalog", "user", "template", "breadboard_model", "demo"]
ResultState = Literal["MATCHES TEMPLATE", "POSSIBLE MISMATCH", "NEEDS REVIEW", "NOT CHECKED"]
Severity = Literal["high", "medium", "low", "info"]
FindingType = Literal[
    "missing_connection",
    "unexpected_connection",
    "wrong_row",
    "wrong_pin",
    "polarity_mismatch",
    "value_mismatch",
    "ambiguous",
    "not_checked",
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Point(BaseModel):
    x: float
    y: float


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


class SourceRef(BaseModel):
    title: str
    url: Optional[str] = None
    checked_on: Optional[str] = None


class TerminalDef(BaseModel):
    name: str
    description: str = ""
    silkscreen_hint: Optional[str] = None


class ElectricalLimit(BaseModel):
    quantity: str
    max_value: float
    unit: str
    source: SourceRef


class PartCatalogItem(BaseModel):
    id: str
    kind: Literal["dev_board", "resistor", "led", "wire"]
    display_name: str
    known_visual_features: list[str]
    terminals: list[TerminalDef]
    polar: bool
    orientation_metadata: Optional[dict] = None
    internal_nets: list[dict] = Field(default_factory=list)
    nominal_value: Optional[dict] = None
    electrical_limits: list[ElectricalLimit] = Field(default_factory=list)
    electrical_limits_note: str = ""
    sources: list[SourceRef] = Field(default_factory=list)
    verification_note: str

    @property
    def terminal_names(self) -> list[str]:
        return [t.name for t in self.terminals]


class BreadboardModel(BaseModel):
    id: str
    display_name: str
    rows: int
    columns: list[str]
    pitch_mm: float
    column_offsets_pitch: dict[str, float]
    connectivity_rules: list[dict]
    unsupported_regions: list[dict]
    calibration_landmarks: list[str]
    sources: list[SourceRef]
    verification_note: str


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


class TemplateInstance(BaseModel):
    ref: str
    part_id: str
    label: str


class ExpectedNode(BaseModel):
    id: str
    instance: str
    terminal: str
    label: str


class ExpectedEdge(BaseModel):
    id: str
    a: str
    b: str
    rule_id: str
    label: str


class TemplateRule(BaseModel):
    id: str
    type: Literal["connection", "component_value", "polarity", "no_unexpected_connections"]
    text: str
    instance: Optional[str] = None
    expected: Optional[dict] = None


class CircuitTemplate(BaseModel):
    id: str
    name: str
    summary: str
    supported_board_id: str
    breadboard_model_id: str
    component_ids: list[str]
    voltage_class: str
    instances: list[TemplateInstance]
    expected_nodes: list[ExpectedNode]
    expected_edges: list[ExpectedEdge]
    explicit_rules: list[TemplateRule]
    reference_layout: dict
    reference_diagram: dict

    def instance(self, ref: str) -> Optional[TemplateInstance]:
        return next((i for i in self.instances if i.ref == ref), None)

    def rule(self, rule_id: str) -> Optional[TemplateRule]:
        return next((r for r in self.explicit_rules if r.id == rule_id), None)


# ---------------------------------------------------------------------------
# Calibration and sessions
# ---------------------------------------------------------------------------


class CalibrationRequest(BaseModel):
    points: dict[str, Point] = Field(
        description="Image-pixel positions of the landmark holes a1, a30, j30 and j1."
    )


class CalibrationMetrics(BaseModel):
    pitch_px_min: float
    opposite_side_ratio: float
    axis_pitch_ratio: float
    holes_checked: int
    holes_visible_fraction: float
    median_offset_pitch: Optional[float]
    phantom_visible_fraction: Optional[float]


class GridHole(BaseModel):
    hole: str
    x: float
    y: float


class RectifiedInfo(BaseModel):
    width: int
    height: int
    px_per_pitch: int
    margin_pitch: float


class CalibrationResult(BaseModel):
    status: Literal["ok", "low_confidence", "failed"]
    messages: list[str]
    metrics: Optional[CalibrationMetrics] = None
    homography: Optional[list[list[float]]] = None  # canonical (pitch units) -> image px
    grid: list[GridHole] = Field(default_factory=list)
    rectified_available: bool = False
    rectified: Optional[RectifiedInfo] = None
    accepted_by_user: bool = False


class ImageSession(BaseModel):
    id: str
    circuit_template_id: str
    image_reference: str
    width: int
    height: int
    calibration_points: Optional[dict[str, Point]] = None
    calibration: Optional[CalibrationResult] = None
    fixture_id: Optional[str] = None
    synthetic: bool = False  # True for the bundled computer-generated demo images; never a real photo
    suggested_landmarks: Optional[dict[str, Point]] = None
    created_at: datetime = Field(default_factory=utcnow)
    saved_project_id: Optional[str] = None
    last_provider: Optional[str] = None


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------


class Evidence(BaseModel):
    source: EvidenceSource
    note: str


class Endpoint(BaseModel):
    kind: Literal["breadboard_hole", "board_pin", "power_rail", "off_grid", "unknown"]
    hole: Optional[str] = None
    board_pin: Optional[str] = None
    point: Optional[Point] = None
    note: Optional[str] = None


class Candidate(BaseModel):
    """What an observation claims is in the photo (part, wire or label)."""

    part_id: Optional[str] = None  # catalog id; None means not in the supported catalog
    kind_hint: Optional[str] = None  # what the model called it, e.g. "capacitor"
    template_ref: Optional[str] = None
    label: Optional[str] = None
    value_text: Optional[str] = None
    color_bands: Optional[list[str]] = None
    value_ohms: Optional[float] = None
    color: Optional[str] = None
    endpoints: dict[str, Endpoint] = Field(default_factory=dict)
    orientation_note: Optional[str] = None
    text: Optional[str] = None
    description: Optional[str] = None


class Observation(BaseModel):
    id: str
    image_session_id: str
    observation_type: ObservationType
    candidate_part_or_endpoint: Candidate
    bounding_box_or_polygon: list[Point] = Field(default_factory=list)
    confidence_label: ConfidenceLabel
    source: ObservationSource
    status: ObservationStatus = "proposed"
    evidence: list[Evidence] = Field(default_factory=list)
    original_candidate: Optional[Candidate] = None
    original_source: Optional[ObservationSource] = None  # who proposed it before a user correction
    display_name: str = ""
    # Which model and runtime proposed this (None for observations made by the user or by OpenCV alone).
    model_name: Optional[str] = None
    runtime: Optional[str] = None
    is_demo_data: bool = False  # True when the proposal is a scripted test fixture, not model output
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ObservationAction(BaseModel):
    action: Literal["confirm", "reject", "correct", "reset"]
    candidate: Optional[Candidate] = None
    note: Optional[str] = None


class NewObservationRequest(BaseModel):
    observation_type: Literal["component", "wire"]
    candidate: Candidate
    note: Optional[str] = None


class AnalyzeRequest(BaseModel):
    # The provider is chosen by the server operator (VISION_PROVIDER), never by the browser.
    accept_unverified_calibration: bool = False


class ProviderInfo(BaseModel):
    name: Literal["ollama", "gemini", "demo"]
    model: Optional[str] = None  # None only for the demo provider (no model runs)
    runtime: str  # e.g. "Ollama (local)", "Gemini API (hosted)", "demo (no model)"
    integration: str
    is_demo: bool
    detail: Optional[str] = None


class AnalyzeResponse(BaseModel):
    observations: list[Observation]
    provider: ProviderInfo
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Graphs, connections and findings
# ---------------------------------------------------------------------------


class GraphNode(BaseModel):
    id: str
    kind: Literal["terminal", "board_pin", "hole", "strip", "unsupported"]
    label: str
    sources: list[str] = Field(default_factory=list)


class GraphEdge(BaseModel):
    id: str
    a: str
    b: str
    kind: Literal["expected", "wire", "component_lead", "breadboard_rule"]
    sources: list[str] = Field(default_factory=list)
    observation_ids: list[str] = Field(default_factory=list)


class CircuitGraphData(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    nets: list[list[str]]  # terminal-level nets (holes and strips omitted)


class Connection(BaseModel):
    id: str
    source_terminal: str
    destination_terminal: str
    source_observation_ids: list[str]
    confirmation_status: Literal["confirmed", "corrected"]
    kind: Literal["wire", "component_lead"]
    description: str


class Finding(BaseModel):
    id: str
    finding_type: FindingType
    severity: Severity
    status: ResultState
    title: str
    expected_connection: Optional[str] = None
    observed_connection: Optional[str] = None
    expected_edge_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    source_observation_ids: list[str] = Field(default_factory=list)
    image_region: list[Point] = Field(default_factory=list)
    explanation: str
    suggestion: Optional[str] = None
    evidence: list[Evidence] = Field(default_factory=list)


class EdgeCheck(BaseModel):
    edge_id: str
    rule_id: str
    expected: str
    state: ResultState
    observed: str
    finding_id: Optional[str] = None


class Report(BaseModel):
    session_id: str
    template_id: str
    overall_status: Literal["MATCHES TEMPLATE", "POSSIBLE MISMATCH", "NEEDS REVIEW"]
    headline: str
    findings: list[Finding]
    edge_checks: list[EdgeCheck]
    expected_graph: CircuitGraphData
    observed_graph: CircuitGraphData
    connections: list[Connection]
    counts: dict[str, int]
    disclaimer: str
    comparison_method: str
    generated_at: datetime = Field(default_factory=utcnow)
