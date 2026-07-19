"""
Step 6 typed state — JSON-serializable handoffs between graph nodes, so the
frontend can render exactly the objects the agents reasoned over.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class AnomalyAlert(BaseModel):
    grid_id: int
    row_idx: int
    col_idx: int
    centroid_lat: float
    centroid_lon: float
    parameter: str = "pm25"
    forecast_value: float
    threshold: float
    timestamp: datetime
    synthetic: bool = False  # demo-injected anomaly, flagged honestly


class EvidenceItem(BaseModel):
    kind: str  # "fire_upwind", "industrial_zone", "highway_density", "wind"
    description: str
    detail: dict = Field(default_factory=dict)


class AttributionResult(BaseModel):
    source_category: str  # biomass_burning | industrial | vehicular | mixed/unknown
    confidence: float  # 0..1
    rationale: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    llm_used: bool = False


class PatrolStop(BaseModel):
    grid_id: int
    centroid_lat: float
    centroid_lon: float
    priority_score: float
    reason: str


class EnforcementPlan(BaseModel):
    ranked_cells: list[PatrolStop]
    route_summary: str
    rationale: str
    llm_used: bool = False


class AgentRunResult(BaseModel):
    alert: AnomalyAlert
    attribution: AttributionResult
    plan: EnforcementPlan
    completed_at: datetime
