"""Common enums, base models, and standard response formats."""
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class MachineStatus(str, Enum):
    HEALTHY = "healthy"
    WATCH = "watch"
    MAINTENANCE_DUE = "maintenance_due"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class MachineDecision(str, Enum):
    MONITOR = "monitor"
    SCHEDULE_MAINTENANCE = "schedule_maintenance"
    URGENT_MAINTENANCE = "urgent_maintenance"
    UNKNOWN = "unknown"


class SafetyStatus(str, Enum):
    SAFE = "safe"
    UNSAFE = "unsafe"
    INDETERMINATE = "indeterminate"
    UNKNOWN = "unknown"


class SafetyOutcome(str, Enum):
    SAFE_TO_INTERRUPT = "SAFE_TO_INTERRUPT"
    UNSAFE_TO_INTERRUPT = "UNSAFE_TO_INTERRUPT"
    INDETERMINATE = "INDETERMINATE"


class JobPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class JobStatus(str, Enum):
    QUEUED = "queued"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class TechnicianStatus(str, Enum):
    AVAILABLE = "available"
    ASSIGNED = "assigned"
    ON_JOB = "on_job"
    UNAVAILABLE = "unavailable"


class SimulationStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class SimulationMode(str, Enum):
    REPLAY = "replay"
    DEMO = "demo"
    LIVE = "live"


class PreemptionDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    NEEDS_REVIEW = "needs_review"


class ApiErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable explanation")
    details: Optional[Any] = Field(None, description="Optional extra error details or validation context")


class ErrorResponse(BaseModel):
    error: ApiErrorDetail
    request_id: str = Field(..., description="Diagnostic request tracing identifier")
