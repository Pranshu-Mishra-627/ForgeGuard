"""Maintenance job schemas across full execution lifecycle."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.schemas.common import JobPriority, JobStatus, SafetyStatus


class JobResponse(BaseModel):
    job_id: str = Field(..., description="Canonical job identifier (e.g., JOB-101)")
    machine_id: str = Field(..., description="Target machine identifier")
    job_type: str = Field(default="preventive", description="Job classification: inspection, preventive, corrective")
    priority: JobPriority = Field(..., description="Priority tier: low, medium, high, critical")
    status: JobStatus = Field(..., description="Execution status: queued, assigned, in_progress, paused, completed, blocked")
    technician_id: Optional[str] = Field(None, description="Assigned technician identifier")
    estimated_duration_minutes: int = Field(default=60, description="Estimated duration in minutes")
    elapsed_minutes: int = Field(default=0, description="Elapsed work time in minutes")
    progress_percent: int = Field(default=0, ge=0, le=100, description="Completion percentage")
    estimated_maintenance_cost: Optional[float] = Field(None, description="Direct maintenance labor/materials cost in currency units")
    estimated_downtime_cost: Optional[float] = Field(None, description="Estimated production downtime cost in currency units")
    safety_status: SafetyStatus = Field(default=SafetyStatus.UNKNOWN, description="Latest assessed safety status")
    created_at: datetime = Field(..., description="Job creation timestamp (ISO-8601)")
    updated_at: datetime = Field(..., description="Last status modification timestamp (ISO-8601)")
    pause_reason: Optional[str] = Field(None, description="Explanation if job was paused or preempted")


class JobDetailResponse(JobResponse):
    timeline: List[Dict[str, Any]] = Field(default_factory=list, description="Historical audit timeline for this job")
    safety_details: Optional[Dict[str, Any]] = Field(None, description="Detailed safety assessment results if evaluated")
