"""Cost analysis and trade-off comparison schemas."""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class CostOption(BaseModel):
    option_id: str = Field(..., description="Option identifier (e.g., maintain_now, defer_maintenance, preempt_active_job)")
    label: str = Field(..., description="Operator-facing option label")
    maintenance_cost: Optional[float] = Field(None, description="Direct maintenance labor and parts cost. Null if unsupported")
    downtime_cost: Optional[float] = Field(None, description="Direct production loss cost. Null if unsupported")
    delay_risk_cost: Optional[float] = Field(None, description="Risk cost of deferral/failure. Null if unsupported")
    interruption_cost: Optional[float] = Field(None, description="Penalty cost of job disruption. Null if unsupported")
    total_estimated_cost: Optional[float] = Field(None, description="Summed total impact. Null if components unavailable")
    assumptions: List[str] = Field(default_factory=list, description="Explicit economic assumptions")


class CostAnalysisResponse(BaseModel):
    currency: str = Field(default="INR", description="Operational currency unit")
    generated_at: datetime = Field(..., description="Timestamp of analysis generation")
    options: List[CostOption] = Field(default_factory=list, description="Comparative operational scenarios")
    recommended_option_id: Optional[str] = Field(None, description="ID of recommended option based on engine evaluation")
    explanation: str = Field(..., description="Authoritative justification from engine or decision logic")
    cost_data_available: bool = Field(default=True, description="False if engine does not supply sufficient cost metrics")
    note: Optional[str] = Field(None, description="Explanatory caveat for missing or unverified financial figures")
