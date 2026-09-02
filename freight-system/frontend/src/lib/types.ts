/**
 * types.ts — TypeScript interfaces mirroring backend Pydantic schemas exactly.
 * DOC3: "TypeScript interfaces mirroring those schemas on the frontend,
 *        generated or hand-kept in sync, no re-shaping inside a component."
 * DOC3 Agentic Rule: every frontend→backend call goes through apiClient.ts,
 *                    never inline fetch() elsewhere.
 */

export type Provenance = 'measured' | 'modeled' | 'assumed';
export type CommitmentMode = 'spot' | 'locked' | 'mixed';
export type SolvedVia = 'milp' | 'hybrid_fallback';

/* ── /scope ─────────────────────────────────────────────── */
export interface ScopeResponse {
  origins:        string[];
  dest_ports:     string[];
  vessel_classes: string[];
}

/* ── /forecast ──────────────────────────────────────────── */
export interface TrajectoryPoint {
  date:  string;   // ISO date
  value: number;
}

/** Additive decomposition produced by Prophet — present in driver_explanation JSON
 *  when Prophet ran successfully during retrain. Per DOC2 §7: explainability only,
 *  never influences model_used. */
export interface ProphetDecomposition {
  trend_delta:                    number;   // $/day change over forecast horizon
  trend_direction:                'rising' | 'falling' | 'flat';
  weekly_seasonality_amplitude:   number;   // peak-to-trough $/day
  regressor_effects:              Record<string, number>;  // {source: $/day additive contribution}
  narrative:                      string;   // human-readable summary
}

/** Parsed shape of ForecastResponse.driver_explanation (JSON string). */
export interface ParsedDriverExplanation {
  text:                   string;
  importances:            Record<string, number>;  // XGBoost feature importances 0–1
  prophet_decomposition?: ProphetDecomposition;    // present when Prophet ran
}

export interface ForecastResponse {
  route:               string;
  vessel_class:        string;
  horizon_days:        number;
  generated_at:        string;  // ISO datetime
  point_estimate:      number;
  confidence_band:     { lower: number; upper: number };
  trajectory:          TrajectoryPoint[];
  driver_explanation:  string | null;
  is_high_uncertainty: boolean;
  model_used:          string;
  provenance:          Provenance;
}


export interface VoyageDetail {
  port:                string;
  vessel_class:        string;
  mode:                CommitmentMode;
  fix_day:             number;
  cost_by_scenario:    { base: number; optimistic: number; pessimistic: number };
  lightening_required: boolean;
  lightening_port:     string | null;
  discharge_days:      number;
  tidal_window_note:   string | null;
  cargo_tonnes?:       number;
  freight_revenue_usd?: number;
  net_sail_value_usd?: number;
}

export interface Strategy {
  voyage_count:                   number;
  commitment_mode:                CommitmentMode;
  voyages:                        VoyageDetail[];
  total_cost_worst_case:          number;
  cost_breakdown: {
    ocean_freight:    number;
    bunker:           number;
    opex?:            number;
    other_cost?:      number;
    port_handling:    number;
    lightening_extra: number;
    tax?:             number;
    risk_buffer:      number;
    total:            number;
    [key: string]:    number | undefined;
  };
  contains_high_uncertainty_voyage: boolean;
  solved_via:                     SolvedVia;
  provenance:                     Provenance;
  provenance_note:                string | null;
  infeasible_reason:              string | null;
  total_freight_revenue_usd?:     number;
  total_net_sail_value_usd?:      number;
  incremental_vs_kill_usd?:       number;
}

export interface RecommendationResponse {
  recommendation:      Strategy;
  scenario_comparison: Strategy[];
}

/* ── /recommendation request ─────────────────────────────── */
export interface HumanOverrides {
  exclude_vessel?:     string[];
  require_port?:       string;
  max_completion_day?: number;
  force_mode?:         'spot' | 'locked';
  min_fix_day?:        number;
}

export interface RecommendationRequest {
  cargo_quantity:           number;
  origin_port:              string;
  discharge_ports:          string[];
  timing_flexibility_days:  number;
  commitment_benchmark_pct?: number;
  constraints?:             HumanOverrides;
}

/* ── /health ─────────────────────────────────────────────── */
export interface HealthResponse {
  status:                 'ok' | 'degraded' | 'error';
  warehouse_reachable:    boolean;
  models_loaded:          boolean;
  last_retrain_at:        string | null;
  ais_listener_last_seen: string | null;
  bunker_last_updated:    string | null;
  message:                string | null;
}

/* ── /port-status ────────────────────────────────────────── */
export interface PortStatusResponse {
  port:             string;
  vessel_count:     number;
  avg_wait_hours:   number;
  recorded_at:      string | null;
  is_live:          boolean;
  source_note:      string | null;
  bunker_price_usd: number | null;
  provenance:       Provenance;
}

/* ── API error shape ─────────────────────────────────────── */
export interface ApiError {
  status:  number;
  message: string;
}

/* ── /chat ───────────────────────────────────────────────── */

export interface ChatMessage {
  role:    'user' | 'assistant';
  content: string;
}

export interface ChatRequest {
  message:              string;
  conversation_history: ChatMessage[];
  /** Last cargo_request from the dashboard form, for follow-up resolution. */
  cargo_context?: RecommendationRequest;
}

export interface ChatResponse {
  reply:                  string;
  tool_called:            boolean;
  /** Populated when a constraint-change re-solve happened — use to update the dashboard. */
  updated_recommendation: RecommendationResponse | null;
  /** Human-readable annotation of what constraints drove the re-solve. */
  constraint_note:        string | null;
  /** Updated history — pass back on the next turn. */
  conversation_history:   ChatMessage[];
}

/* ── /fleet-schedule (Step 51V) ─────────────────────────── */

export interface ContractAssignment {
  contract_id: string;
  route_id: string;
  origin: string;
  destination: string;
  cargo_type: string;
  contract_volume_mt: number;
  imo: string | null;
  vessel_name: string | null;
  vessel_dwt: number | null;
  vessel_class: string | null;
  departure_date: string | null;
  estimated_eta: string | null;
  bunker_cost_usd: number;
  opex_cost_usd: number;
  other_cost_usd: number;
  total_voyage_cost_usd: number;
  bear_sail: number;
  base_sail: number;
  bull_sail: number;
  bear_incremental: number;
  base_incremental: number;
  bull_incremental: number;
  worst_incremental: number;
  expected_incremental: number;
  decision: string;
}

export interface VesselScheduleItem {
  imo: string;
  vessel_name: string;
  departure_date: string;
  estimated_eta: string;
  contract_id: string;
  route_id: string;
  origin: string;
  destination: string;
  contract_volume_mt: number;
  worst_incremental: number;
  expected_incremental: number;
  voyage_sequence: number;
}

export interface FleetScheduleSummary {
  total_contracts: number;
  sail_contracts: number;
  kill_contracts: number;
  sail_vessels: number;
  bear_incremental_usd: number;
  base_incremental_usd: number;
  bull_incremental_usd: number;
  worst_incremental_usd: number;
  expected_incremental_usd: number;
  bunker_cost_usd: number;
  opex_cost_usd: number;
  total_voyage_cost_usd: number;
  bunker_price_vlsfo_usd: number;
  solver_status: string;
}

export interface FleetScheduleResponse {
  summary: FleetScheduleSummary;
  assignments: ContractAssignment[];
  vessel_schedule: VesselScheduleItem[];
  all_decisions: Record<string, any>[];
}

/* ── /fleet-status (Phase 1 MVP) ────────────────────────── */

export interface LiveVesselStatus {
  imo: number;
  vessel_name: string;
  vessel_class: string;
  dwt: number;
  current_lat: number;
  current_lon: number;
  speed_knots: number;
  recorded_at: string;
  status: string;
  destination: string;
}

export interface VesselClassEntry {
  class_name: string;
  typical_capacity_tonnes: number;
  draft_m: number;
  loa_m: number;
  beam_m: number;
}

export interface FleetStatusResponse {
  vessels: LiveVesselStatus[];         // Live AIS-tracked (may be empty)
  vessel_classes: VesselClassEntry[];  // Canonical catalog — always present
  ais_live: boolean;
}

export const FALLBACK_SCOPE: ScopeResponse = {
  origins: ['Australia (Hay Point)', 'Indonesia (Samarinda)', 'South Africa (Richards Bay)'],
  dest_ports: ['Dhamra', 'Gangavaram', 'Paradip'],
  vessel_classes: ['Capesize', 'Panamax/Kamsarmax', 'Supramax/Ultramax']
};

/* ── /provenance ────────────────────────────────────────── */

export interface CitationItem {
  id: string;
  token: string;
  title: string;
  source: string;
  equation?: string | null;
  provenance: Provenance;
  confidence: string;
  rationale: string;
}

export interface ComparativeMetric {
  label: string;
  baseline: string;
  assumed: string;
  delta: string;
  favorable: boolean;
}

export interface SituationalScenario {
  id: string;
  title: string;
  category: string;
  subtitle: string;
  base_case_text: string;
  assumed_situation_title: string;
  assumed_situation_text: string;
  comparative_metrics: ComparativeMetric[];
  citations: Record<string, CitationItem>;
}

export interface ParameterItem {
  name: string;
  category: string;
  value: string;
  unit: string;
  provenance: Provenance;
  source: string;
  verified: boolean;
  notes: string;
}

export interface ProvenanceSituationsResponse {
  scenarios: SituationalScenario[];
}

export interface ProvenanceCatalogResponse {
  parameters: ParameterItem[];
  total_count: number;
}

