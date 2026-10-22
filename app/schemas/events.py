"""Audit and simulation event log schemas."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(..., description="Event timestamp (ISO-8601)")
    event_type: str = Field(..., description="Event classification (e.g., prediction, alert_decision, schedule_planned, safety_assessed, preemption_evaluated, preemption_executed, simulation_step)")
    machine_id: Optional[str] = Field(None, description="Related machine identifier if applicable")
    job_id: Optional[str] = Field(None, description="Related job identifier if applicable")
    technician_id: Optional[str] = Field(None, description="Related technician identifier if applicable")
    outcome: Optional[str] = Field(None, description="Outcome of operation (e.g., success, denied, safe, critical)")
    reason: Optional[str] = Field(None, description="Human or model reasoning explanation")
    severity: str = Field(default="info", description="Severity level: info, warning, critical")
    details: Dict[str, Any] = Field(default_factory=dict, description="Structured contextual event payload")


class EventsResponse(BaseModel):
    events: List[AuditEvent] = Field(default_factory=list, description="List of recorded events matching query filters")
    total: int = Field(..., description="Count of returned events")
    cursor: Optional[str] = Field(None, description="Cursor token for next page of event records")
