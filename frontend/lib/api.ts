const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

async function post<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, { method: "POST" });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

export interface HealthResponse {
  status: string;
  environment: string;
  service: string;
}

export interface GridCellInfo {
  grid_id: number;
  row_idx: number;
  col_idx: number;
  centroid_lat: number;
  centroid_lon: number;
}

export interface GridCellsResponse {
  city_slug: string;
  cell_count: number;
  cells: GridCellInfo[];
}

export interface GridReadingsResponse {
  city_slug: string;
  parameter: string;
  measured_at: string | null;
  readings: { grid_id: number; value: number; contributing_sensor_count: number }[];
}

export interface ForecastResponse {
  city_slug: string;
  generated_from: string;
  horizon_hours: number;
  grid_shape: [number, number];
  valid_mask: boolean[][];
  horizons: Record<string, { timestep: string; pm25: number[][] }>;
}

export interface ForecastMetrics {
  model_available: boolean;
  model_rmse_1h: number;
  persistence_rmse_1h: number;
  beats_persistence: boolean;
  windows: number;
  test_windows: number;
  // 24h-direct model (the PS brief's judged horizon), present once trained
  model_rmse_24h?: number;
  persistence_rmse_24h?: number;
  beats_persistence_24h?: boolean;
}

export interface EvidenceItem {
  kind: string;
  description: string;
  detail: Record<string, unknown>;
}

export interface AgentRun {
  alert: {
    grid_id: number;
    centroid_lat: number;
    centroid_lon: number;
    forecast_value: number;
    threshold: number;
    timestamp: string;
    synthetic: boolean;
  };
  attribution: {
    source_category: string;
    confidence: number;
    rationale: string;
    evidence: EvidenceItem[];
    llm_used: boolean;
  };
  plan: {
    ranked_cells: {
      grid_id: number;
      centroid_lat: number;
      centroid_lon: number;
      priority_score: number;
      reason: string;
    }[];
    route_summary: string;
    rationale: string;
    llm_used: boolean;
  };
  completed_at: string;
}

export interface AdvisoryResponse {
  city_slug: string;
  lang: string;
  measured_at?: string;
  mean_pm25?: number;
  max_pm25?: number;
  category?: string;
  advisory: string | null;
  llm_used?: boolean;
}

export const getHealth = () => get<HealthResponse>("/health");
export const getGridCells = (city = "delhi-ncr") =>
  get<GridCellsResponse>(`/grid/cells?city_slug=${city}`);
export const getGridReadings = (city = "delhi-ncr", parameter = "pm25") =>
  get<GridReadingsResponse>(`/grid/readings?city_slug=${city}&parameter=${parameter}`);
export const getForecast = (city = "delhi-ncr", horizon = 24) =>
  get<ForecastResponse>(`/forecast/grid?city_slug=${city}&horizon_hours=${horizon}`);
export const getForecastMetrics = (city = "delhi-ncr") =>
  get<ForecastMetrics>(`/forecast/metrics?city_slug=${city}`);
export const getRecommendations = (city = "delhi-ncr") =>
  get<{ city_slug: string; runs: AgentRun[] }>(`/agents/recommendations?city_slug=${city}`);
export const runAgentDrill = (city = "delhi-ncr", syntheticGridId?: number) =>
  post<AgentRun & { anomaly_found: boolean; message?: string }>(
    `/agents/run?city_slug=${city}${syntheticGridId ? `&synthetic_grid_id=${syntheticGridId}` : ""}`
  );
export type AdvisoryLang = "en" | "hi" | "kn" | "ta" | "bn" | "mr";

export const getAdvisory = (city = "delhi-ncr", lang: AdvisoryLang = "en") =>
  get<AdvisoryResponse>(`/advisory?city_slug=${city}&lang=${lang}`);

// --- Backend contract additions (SITEMAP "NEEDED" items now live) ---

export interface StatsSummary {
  city_slug: string;
  parameter: string;
  measured_at: string | null;
  mean?: number;
  max?: number;
  cells_reporting?: number;
  category?: string | null;
  trend_delta_24h?: number | null;
  trend_compared_to?: string | null;
}

export interface StationInfo {
  location_id: number;
  station_name: string;
  latitude: number;
  longitude: number;
  last_measured_at: string | null;
  parameter_count: number;
}

export interface CityHeadline {
  city_slug: string;
  display_name: string;
  bbox: [number, number, number, number];
  live: boolean;
  model_available: boolean;
  measured_at: string | null;
  mean_pm25: number | null;
  max_pm25: number | null;
  cells_reporting: number;
  category?: string;
}

export interface IngestionSourceSummary {
  source: string;
  table_rows: number;
  latest_data_at: string | null;
  last_run: {
    started_at: string;
    finished_at: string | null;
    status: string;
    records_ingested: number;
    error_message: string | null;
  } | null;
}

export type RunStatus = "new" | "dispatched" | "inspected" | "closed";

export interface TrackedAgentRun extends AgentRun {
  run_id: number;
  status: RunStatus;
  assigned_to: string | null;
  dispatched_at: string | null;
  inspected_at: string | null;
  closed_at: string | null;
  signal_to_dispatch_minutes: number | null;
}

export interface AgentRunsPage {
  city_slug: string;
  total: number;
  limit: number;
  offset: number;
  mean_signal_to_dispatch_minutes: number | null;
  runs: TrackedAgentRun[];
}

export interface CellForecast {
  city_slug: string;
  grid_id: number;
  centroid_lat: number;
  centroid_lon: number;
  horizon_hours: number;
  generated_from: string;
  last_observed_pm25: number | null;
  history: { timestep: string; pm25: number }[];
  forecast: { timestep: string; pm25: number }[];
}

export const getStatsSummary = (city = "delhi-ncr", parameter = "pm25") =>
  get<StatsSummary>(`/stats/summary?city_slug=${city}&parameter=${parameter}`);
export const getStations = (city = "delhi-ncr") =>
  get<{ city_slug: string; station_count: number; stations: StationInfo[] }>(
    `/stations?city_slug=${city}`
  );
export const getCities = () => get<{ cities: CityHeadline[] }>("/cities");
export const getIngestionSummary = (city = "delhi-ncr") =>
  get<{ city_slug: string; sources: IngestionSourceSummary[] }>(
    `/ingestion/summary?city_slug=${city}`
  );
export const getAgentRuns = (city = "delhi-ncr", limit = 20, offset = 0) =>
  get<AgentRunsPage>(`/agents/runs?city_slug=${city}&limit=${limit}&offset=${offset}`);
export const updateRunStatus = (runId: number, status: RunStatus, assignee?: string) =>
  post<TrackedAgentRun>(
    `/agents/runs/${runId}/status?status=${status}${assignee ? `&assignee=${encodeURIComponent(assignee)}` : ""}`
  );
export const getCellForecast = (gridId: number, city = "delhi-ncr", horizon = 24) =>
  get<CellForecast>(`/forecast/cell/${gridId}?city_slug=${city}&horizon_hours=${horizon}`);
