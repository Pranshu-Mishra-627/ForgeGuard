"""Maintenance shift schedule schemas."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ScheduleAssignment(BaseModel):
    job_id: str = Field(..., description="Target maintenance job ID")
    machine_id: str = Field(..., description="Machine identifier")
    technician_id: Optional[str] = Field(None, description="Assigned technician identifier")
    planned_start_at: Optional[datetime] = Field(None, description="Planned start timestamp")
    planned_end_at: Optional[datetime] = Field(None, description="Planned end timestamp")
    status: str = Field(default="planned", description="Assignment status: planned, in_progress, paused, completed")
    priority_score: Optional[float] = Field(None, description="Engine computed priority score")
    reason: Optional[str] = Field(None, description="Dispatch or deferral rationale from engine")


class ScheduleResponse(BaseModel):
    generated_at: datetime = Field(..., description="Schedule calculation timestamp (ISO-8601)")
    assignments: List[ScheduleAssignment] = Field(default_factory=list, description="List of scheduled assignments")
    selected_machines: List[str] = Field(default_factory=list, description="Machines selected for service in priority order")
    deferred_machines: List[str] = Field(default_factory=list, description="Alerted machines deferred due to capacity")
    unalerted_machines: List[str] = Field(default_factory=list, description="Machines not triggered for alert")
    capacity_summary: Dict[str, Any] = Field(default_factory=dict, description="Technician slot allocation summary")


class ReplanRequest(BaseModel):
    reason: str = Field(default="periodic", description="Trigger reason (e.g., new_critical_job, shift_start, manual)")
    trigger_job_id: Optional[str] = Field(None, description="Optional job ID that triggered the replan request")
