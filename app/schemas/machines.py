"""Machine schemas for health, telemetry, prediction, and operational state."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.schemas.common import MachineDecision, MachineStatus, SafetyStatus


class TelemetryReading(BaseModel):
    air_temperature: float = Field(..., description="Air temperature in Kelvin")
    process_temperature: float = Field(..., description="Process temperature in Kelvin")
    rotational_speed: float = Field(..., description="Rotational speed in RPM")
    torque: float = Field(..., description="Torque in Nm")
    tool_wear: float = Field(..., description="Tool wear in minutes")
    machine_type: str = Field(default="M", description="Machine product variant: L, M, or H")


class MachineResponse(BaseModel):
    machine_id: str = Field(..., description="Canonical machine identifier (e.g., M-01)")
    name: str = Field(..., description="Human-readable machine name")
    status: MachineStatus = Field(..., description="Operational status: healthy, watch, maintenance_due, critical, unknown")
    failure_probability: Optional[float] = Field(None, description="ML predicted failure probability (0.0 to 1.0)")
    predicted_failure_mode: Optional[str] = Field(None, description="Predicted failure mode code (e.g., TWF, HDF, PWF, OSF, RNF)")
    last_telemetry_at: Optional[datetime] = Field(None, description="Timestamp of latest sensor reading")
    decision: MachineDecision = Field(default=MachineDecision.UNKNOWN, description="Engine operational decision")
    remaining_useful_life_hours: Optional[float] = Field(None, description="Remaining useful life in hours, null if unsupported")
    safety_status: SafetyStatus = Field(default=SafetyStatus.UNKNOWN, description="Assessed safety status")
    active_job_id: Optional[str] = Field(None, description="ID of currently executing maintenance job, if any")
    telemetry: Optional[Dict[str, Any]] = Field(None, description="Latest sensor telemetry values")


class MachineDetailResponse(MachineResponse):
    recent_events: List[Dict[str, Any]] = Field(default_factory=list, description="Recent audit events for this machine")
    equipment_metadata: Dict[str, Any] = Field(default_factory=dict, description="Hardware specs and critical equipment flags")
