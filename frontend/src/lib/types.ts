// Mirrors backend/app/schemas.py. Keep the two in sync.

export type Point = { x: number; y: number };
export type Confidence = "high" | "medium" | "low" | "uncertain";
export type Source = "gemma" | "opencv" | "user" | "demo";
export type ObsStatus = "proposed" | "confirmed" | "rejected" | "corrected";
export type ObsType = "board" | "component" | "wire" | "label_text" | "obscured_region";
export type ResultState = "MATCHES TEMPLATE" | "POSSIBLE MISMATCH" | "NEEDS REVIEW" | "NOT CHECKED";

export type Endpoint = {
  kind: "breadboard_hole" | "board_pin" | "power_rail" | "off_grid" | "unknown";
  hole?: string | null;
  board_pin?: string | null;
  point?: Point | null;
  note?: string | null;
};

export type Candidate = {
  part_id?: string | null;
  kind_hint?: string | null;
  template_ref?: string | null;
  label?: string | null;
  value_text?: string | null;
  color_bands?: string[] | null;
  value_ohms?: number | null;
  color?: string | null;
  endpoints: Record<string, Endpoint>;
  orientation_note?: string | null;
  text?: string | null;
  description?: string | null;
};

export type Evidence = { source: Source | "catalog" | "template" | "breadboard_model"; note: string };

export type Observation = {
  id: string;
  image_session_id: string;
  observation_type: ObsType;
  candidate_part_or_endpoint: Candidate;
  bounding_box_or_polygon: Point[];
  confidence_label: Confidence;
  source: Source;
  status: ObsStatus;
  evidence: Evidence[];
  original_candidate?: Candidate | null;
  original_source?: Source | null;
  display_name: string;
  model_name?: string | null; // model that proposed this (null for user / OpenCV-only observations)
  runtime?: string | null;
  is_demo_data?: boolean; // scripted synthetic fixture, not model output
};

export type CalibrationMetrics = {
  pitch_px_min: number;
  holes_visible_fraction: number;
  holes_checked: number;
  phantom_visible_fraction: number | null;
};

export type Calibration = {
  status: "ok" | "low_confidence" | "failed";
  messages: string[];
  metrics?: CalibrationMetrics | null;
  grid: { hole: string; x: number; y: number }[];
  rectified?: { width: number; height: number; px_per_pitch: number; margin_pitch: number } | null;
  accepted_by_user: boolean;
};

export type Session = {
  id: string;
  circuit_template_id: string;
  width: number;
  height: number;
  fixture_id?: string | null;
  synthetic?: boolean; // computer-generated demo image, never a real photo
  suggested_landmarks?: Record<string, Point> | null;
  calibration?: Calibration | null;
  calibration_points?: Record<string, Point> | null;
};

export type ProviderName = "ollama" | "gemini" | "demo";
export type ProviderInfo = { name: ProviderName; model?: string | null; runtime: string; integration: string; is_demo: boolean; detail?: string | null };
export type AnalyzeResponse = { observations: Observation[]; provider: ProviderInfo; warnings: string[] };

export type Finding = {
  id: string;
  finding_type: string;
  severity: "high" | "medium" | "low" | "info";
  status: ResultState;
  title: string;
  expected_connection?: string | null;
  observed_connection?: string | null;
  expected_edge_ids: string[];
  rule_ids: string[];
  source_observation_ids: string[];
  image_region: Point[];
  explanation: string;
  suggestion?: string | null;
  evidence: Evidence[];
};

export type EdgeCheck = { edge_id: string; rule_id: string; expected: string; state: ResultState; observed: string; finding_id?: string | null };
export type GraphData = {
  nodes: { id: string; kind: string; label: string; sources: string[] }[];
  edges: { id: string; a: string; b: string; kind: string; sources: string[]; observation_ids: string[] }[];
  nets: string[][];
};

export type Report = {
  session_id: string;
  template_id: string;
  overall_status: "MATCHES TEMPLATE" | "POSSIBLE MISMATCH" | "NEEDS REVIEW";
  headline: string;
  findings: Finding[];
  edge_checks: EdgeCheck[];
  expected_graph: GraphData;
  observed_graph: GraphData;
  connections: { id: string; source_terminal: string; destination_terminal: string; description: string; confirmation_status: string; source_observation_ids: string[] }[];
  counts: Record<string, number>;
  disclaimer: string;
  comparison_method: string;
};

export type TemplateSummary = { id: string; name: string; summary: string; voltage_class: string; supported_board_id: string };

export type PartDef = {
  id: string;
  kind: string;
  display_name: string;
  known_visual_features: string[];
  terminals: { name: string; description: string; silkscreen_hint?: string | null }[];
  polar: boolean;
  electrical_limits_note: string;
  verification_note: string;
  sources: { title: string; url?: string | null; checked_on?: string | null }[];
};

export type TemplateDetail = {
  template: {
    id: string;
    name: string;
    summary: string;
    voltage_class: string;
    instances: { ref: string; part_id: string; label: string }[];
    expected_nodes: { id: string; instance: string; terminal: string; label: string }[];
    expected_edges: { id: string; a: string; b: string; rule_id: string; label: string }[];
    explicit_rules: { id: string; type: string; text: string }[];
    reference_layout: { description: string; placements: Record<string, unknown>[] };
    reference_diagram: Diagram;
  };
  parts: Record<string, PartDef>;
  breadboard: { id: string; display_name: string; rows: number; columns: string[]; column_offsets_pitch: Record<string, number>; verification_note: string; unsupported_regions: { id: string; description: string }[]; connectivity_rules: { id: string; description: string }[] };
};

export type Diagram = {
  viewBox: string;
  symbols: {
    id: string;
    type: "board" | "resistor" | "led";
    x?: number; y?: number; w?: number; h?: number;
    x1?: number; y1?: number; x2?: number; y2?: number;
    label: string;
    pins?: { terminal: string; label: string; x: number; y: number }[];
    terminals?: Record<string, [number, number]>;
  }[];
  wires: { edge_id: string; points: [number, number][] }[];
};

export type Sample = { id: string; title: string; description: string; filename: string; synthetic: boolean };
export type Health = {
  status: string;
  provider: ProviderName;
  model: string | null;
  runtime: string | null;
  demo_mode: boolean;
  reachable: boolean;
  model_installed: boolean;
  model_loaded: boolean;
  ready: boolean;
  message: string;
  setup_hint: string | null;
  timeout_seconds: number;
  max_upload_mb: number;
  allowed_types: string[];
};
