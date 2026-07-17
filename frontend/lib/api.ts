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
export const getAdvisory = (city = "delhi-ncr", lang: "en" | "hi" = "en") =>
  get<AdvisoryResponse>(`/advisory?city_slug=${city}&lang=${lang}`);
