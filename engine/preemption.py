"""Preemptive Maintenance Scheduling for ForgeGuard Decision Engine (Person 2).

Evaluates whether an active, lower-priority maintenance job should be safely paused
and interrupted to reassign a technician to an urgent or newly failed machine.

Key Invariants & Rules:
    1. Single-Active-Job Invariant: A technician must never be assigned to two active jobs
       simultaneously. Preemption reassigns the technician, never creating extra capacity.
    2. Interruptibility Safety: Jobs are interrupted only if explicitly marked interruptible
       or verified as safe. If safety or interruptibility cannot be established, preemption
       is denied and escalated.
    3. Work Preservation: Interrupted jobs preserve progress, start times, and metadata;
       they are placed in a reschedule queue, never marked completed or discarded.
    4. Guardrail & Human Approval: If configured or required by safety policy, preemption
       returns a pending recommendation rather than executing unauthorized mutation.
    5. Calibrated Risk Phrasing: Distinguishes actual failures from predicted risks and never
       asserts that predicted failures are certain.
    6. State Integrity: Clearly distinguishes recommendations, pending approval, and executed
       preemption. Assignment state changes only when preemption is actually executed.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from engine.policy_guardrails import (
    DEFAULT_POLICY_CONFIG,
    MaintenancePolicyConfig,
    VIOLATION_TYPE_MANDATORY_REVIEW,
    VIOLATION_TYPE_POLICY_VIOLATION,
)
from engine.safety_assessment import (
    DEFAULT_EQUIPMENT_SAFETY_CONFIG,
    OUTCOME_INDETERMINATE,
    OUTCOME_SAFE_TO_INTERRUPT,
    OUTCOME_UNSAFE_TO_INTERRUPT,
    EquipmentSafetyConfig,
    EquipmentSafetyRule,
    MachineTelemetryContext,
    SafetyAssessmentOutcome,
    SafetyAssessmentResult,
    assess_job_safety,
)

# Preemption Status Constants
STATUS_EXECUTED = "executed"
STATUS_PENDING_APPROVAL = "pending_approval"
STATUS_RECOMMENDED = "recommended"
STATUS_DENIED = "denied"
STATUS_NO_PREEMPTION = "no_preemption"

# Job Status Constants
JOB_STATUS_PENDING = "pending"
JOB_STATUS_DISPATCHED = "dispatched"
JOB_STATUS_IN_PROGRESS = "in_progress"
JOB_STATUS_ACTIVE = "active"
JOB_STATUS_INTERRUPTED = "interrupted"
JOB_STATUS_PAUSED = "paused"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_CANCELED = "canceled"

# Alert Category Constants
ALERT_CATEGORY_ACTUAL_FAILURE = "actual_failure"
ALERT_CATEGORY_CRITICAL_ALERT = "critical_alert"
ALERT_CATEGORY_PREDICTED_HIGH_RISK = "predicted_high_risk"
ALERT_CATEGORY_ROUTINE = "routine"


@dataclass(frozen=True)
class PreemptionConfig:
    """Configuration governing preemptive maintenance scheduling rules.

    Attributes:
        enabled: Whether preemption evaluation and execution is enabled.
        min_priority_delta: Minimum difference (incoming - current) required to justify preemption.
        allowed_alert_categories: Categories of alerts permitted to trigger preemption.
        require_human_approval: If True, preemption requires explicit human authorization.
        interruptible_job_states: Job execution states that can be safely paused.
        interruptible_job_types: Types of maintenance work eligible for safe interruption.
        non_interruptible_job_types: High-risk or safety-critical work types that must never pause.
        allow_unknown_interruptibility: If False, jobs with missing interruptibility metadata cannot pause.
        guardrail_config: Optional MaintenancePolicyConfig to integrate with compliance policies.
        equipment_safety_config: Optional EquipmentSafetyConfig for data-driven telemetry safety checks.
    """

    enabled: bool = True
    min_priority_delta: float = 0.0
    allowed_alert_categories: tuple[str, ...] = (
        ALERT_CATEGORY_ACTUAL_FAILURE,
        ALERT_CATEGORY_CRITICAL_ALERT,
        ALERT_CATEGORY_PREDICTED_HIGH_RISK,
    )
    require_human_approval: bool = False
    interruptible_job_states: tuple[str, ...] = (
        JOB_STATUS_IN_PROGRESS,
        JOB_STATUS_ACTIVE,
        JOB_STATUS_DISPATCHED,
        JOB_STATUS_PENDING,
    )
    interruptible_job_types: tuple[str, ...] = (
        "routine_inspection",
        "preventive_maintenance",
        "standard_repair",
        "scheduled_servicing",
        "lubrication",
        "filter_replacement",
    )
    non_interruptible_job_types: tuple[str, ...] = (
        "emergency_repair",
        "critical_overhaul",
        "safety_containment",
        "hazardous_material_service",
    )
    allow_unknown_interruptibility: bool = False
    guardrail_config: MaintenancePolicyConfig | None = None
    equipment_safety_config: EquipmentSafetyConfig | None = None

    def __post_init__(self) -> None:
        """Validate preemption configuration parameters."""
        if not isinstance(self.enabled, bool):
            raise TypeError(f"enabled must be a boolean, got {type(self.enabled).__name__}.")

        if isinstance(self.min_priority_delta, bool) or not isinstance(
            self.min_priority_delta, (int, float, np.number)
        ):
            raise TypeError(
                f"min_priority_delta must be numeric, got {type(self.min_priority_delta).__name__}."
            )

        if not math.isfinite(self.min_priority_delta):
            raise ValueError(f"min_priority_delta must be finite, got {self.min_priority_delta}.")

        if self.min_priority_delta < 0.0:
            raise ValueError(
                f"min_priority_delta must be non-negative (>= 0.0), got {self.min_priority_delta}."
            )

        if not isinstance(self.require_human_approval, bool):
            raise TypeError(
                f"require_human_approval must be a boolean, got {type(self.require_human_approval).__name__}."
            )

        if not isinstance(self.allow_unknown_interruptibility, bool):
            raise TypeError(
                f"allow_unknown_interruptibility must be a boolean, got {type(self.allow_unknown_interruptibility).__name__}."
            )

        if self.equipment_safety_config is not None and not isinstance(
            self.equipment_safety_config, EquipmentSafetyConfig
        ):
            raise TypeError(
                f"equipment_safety_config must be an EquipmentSafetyConfig, got {type(self.equipment_safety_config).__name__}."
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert preemption configuration to dictionary representation."""
        return {
            "enabled": self.enabled,
            "min_priority_delta": self.min_priority_delta,
            "allowed_alert_categories": list(self.allowed_alert_categories),
            "require_human_approval": self.require_human_approval,
            "interruptible_job_states": list(self.interruptible_job_states),
            "interruptible_job_types": list(self.interruptible_job_types),
            "non_interruptible_job_types": list(self.non_interruptible_job_types),
            "allow_unknown_interruptibility": self.allow_unknown_interruptibility,
            "guardrail_config": self.guardrail_config.to_dict() if self.guardrail_config else None,
            "equipment_safety_config": self.equipment_safety_config.to_dict() if self.equipment_safety_config else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PreemptionConfig:
        """Create PreemptionConfig dynamically from mapping."""
        from pathlib import Path

        g_raw = data.get("guardrail_config")
        if isinstance(g_raw, MaintenancePolicyConfig):
            g_cfg = g_raw
        elif isinstance(g_raw, (str, Path)):
            g_cfg = MaintenancePolicyConfig.from_file(g_raw)
        elif isinstance(g_raw, Mapping):
            g_cfg = MaintenancePolicyConfig.from_dict(g_raw)
        else:
            g_cfg = None

        s_raw = data.get("equipment_safety_config")
        if isinstance(s_raw, EquipmentSafetyConfig):
            s_cfg = s_raw
        elif isinstance(s_raw, (str, Path)):
            s_cfg = EquipmentSafetyConfig.from_file(s_raw)
        elif isinstance(s_raw, Mapping):
            s_cfg = EquipmentSafetyConfig.from_dict(s_raw)
        else:
            s_cfg = None

        return cls(
            enabled=bool(data.get("enabled", True)),
            min_priority_delta=float(data.get("min_priority_delta", 0.0)),
            allowed_alert_categories=tuple(data.get("allowed_alert_categories", (
                ALERT_CATEGORY_ACTUAL_FAILURE,
                ALERT_CATEGORY_CRITICAL_ALERT,
                ALERT_CATEGORY_PREDICTED_HIGH_RISK,
            ))),
            require_human_approval=bool(data.get("require_human_approval", False)),
            interruptible_job_states=tuple(data.get("interruptible_job_states", (
                JOB_STATUS_IN_PROGRESS,
                JOB_STATUS_ACTIVE,
                JOB_STATUS_DISPATCHED,
                JOB_STATUS_PENDING,
            ))),
            interruptible_job_types=tuple(data.get("interruptible_job_types", (
                "routine_inspection",
                "preventive_maintenance",
                "standard_repair",
                "scheduled_servicing",
                "lubrication",
                "filter_replacement",
            ))),
            non_interruptible_job_types=tuple(data.get("non_interruptible_job_types", (
                "emergency_repair",
                "critical_overhaul",
                "safety_containment",
                "hazardous_material_service",
            ))),
            allow_unknown_interruptibility=bool(data.get("allow_unknown_interruptibility", False)),
            guardrail_config=g_cfg,
            equipment_safety_config=s_cfg,
        )

    @classmethod
    def from_file(cls, filepath: str | Any) -> PreemptionConfig:
        """Load PreemptionConfig dynamically from external JSON configuration file."""
        import json
        from pathlib import Path

        path = Path(filepath)
        if not path.is_file():
            raise FileNotFoundError(f"Preemption configuration file not found: {filepath}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_file(self, filepath: str | Any) -> None:
        """Export PreemptionConfig to an external JSON configuration file."""
        import json
        from pathlib import Path

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)


DEFAULT_PREEMPTION_CONFIG = PreemptionConfig()


@dataclass
class MaintenanceJob:
    """Represents a maintenance job or technician work order.

    Attributes:
        job_id: Unique job identifier.
        machine_id: Target machine identifier.
        priority_score: Expected failure impact or urgency priority score.
        failure_probability: Estimated failure probability (if derived from ML model).
        status: Current job status ('in_progress', 'dispatched', 'interrupted', etc.).
        job_type: Type of maintenance work ('preventive_maintenance', 'emergency_repair', etc.).
        is_interruptible: Explicit flag. If None, derived from job_type and safety configuration.
        alert_category: Urgency classification ('actual_failure', 'predicted_high_risk', etc.).
        technician_id: Assigned technician identifier, or None.
        progress: Progress state (e.g. percentage or steps) if provided. None if not supplied.
        started_at: Job start timestamp if provided. None if not supplied.
        interrupted_at: Job pause timestamp if provided. None if not supplied.
        interruption_reason: Reason why job was paused, if interrupted.
        preempted_by_job_id: ID of higher-priority job causing the preemption.
        metadata: Arbitrary operational metadata dictionary.
    """

    job_id: Any
    machine_id: Any
    priority_score: float
    failure_probability: float | None = None
    status: str = JOB_STATUS_PENDING
    job_type: str = "preventive_maintenance"
    is_interruptible: bool | None = None
    alert_category: str = ALERT_CATEGORY_PREDICTED_HIGH_RISK
    technician_id: str | None = None
    progress: Any = None
    started_at: Any = None
    interrupted_at: Any = None
    interruption_reason: str | None = None
    preempted_by_job_id: Any = None
    safety_context: MachineTelemetryContext | Mapping[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate job attributes."""
        if isinstance(self.priority_score, bool) or not isinstance(
            self.priority_score, (int, float, np.number)
        ):
            raise TypeError(f"priority_score must be numeric, got {type(self.priority_score).__name__}.")

        try:
            self.priority_score = float(self.priority_score)
        except (ValueError, TypeError) as exc:
            raise TypeError(f"priority_score must be numeric, got {self.priority_score!r}.") from exc

        if not math.isfinite(self.priority_score):
            raise ValueError(f"priority_score must be finite, got {self.priority_score}.")

        if self.failure_probability is not None:
            if isinstance(self.failure_probability, bool) or not isinstance(
                self.failure_probability, (int, float, np.number)
            ):
                raise TypeError(
                    f"failure_probability must be numeric, got {type(self.failure_probability).__name__}."
                )
            try:
                fp = float(self.failure_probability)
            except (ValueError, TypeError) as exc:
                raise TypeError(f"failure_probability must be numeric, got {self.failure_probability!r}.") from exc

            if not math.isfinite(fp) or not (0.0 <= fp <= 1.0):
                raise ValueError(f"failure_probability must be in [0.0, 1.0], got {fp}.")
            self.failure_probability = fp

    def copy(self) -> MaintenanceJob:
        """Return an independent deep copy of the job."""
        return copy.deepcopy(self)

    @property
    def is_active(self) -> bool:
        """True if the job is actively occupying technician capacity."""
        return self.status in (JOB_STATUS_IN_PROGRESS, JOB_STATUS_ACTIVE, JOB_STATUS_DISPATCHED)

    @property
    def is_interrupted(self) -> bool:
        """True if the job has been paused/interrupted and awaits rescheduling."""
        return self.status in (JOB_STATUS_INTERRUPTED, JOB_STATUS_PAUSED)

    def to_dict(self) -> dict[str, Any]:
        """Convert job to dictionary representation."""
        ctx_dict = None
        if self.safety_context is not None:
            if hasattr(self.safety_context, "to_dict"):
                ctx_dict = self.safety_context.to_dict()
            elif isinstance(self.safety_context, Mapping):
                ctx_dict = dict(self.safety_context)
            else:
                ctx_dict = str(self.safety_context)

        return {
            "job_id": self.job_id,
            "machine_id": self.machine_id,
            "priority_score": self.priority_score,
            "failure_probability": self.failure_probability,
            "status": self.status,
            "job_type": self.job_type,
            "is_interruptible": self.is_interruptible,
            "alert_category": self.alert_category,
            "technician_id": self.technician_id,
            "progress": self.progress,
            "started_at": self.started_at,
            "interrupted_at": self.interrupted_at,
            "interruption_reason": self.interruption_reason,
            "preempted_by_job_id": self.preempted_by_job_id,
            "safety_context": ctx_dict,
            "metadata": dict(self.metadata),
        }

    def __getitem__(self, key: str) -> Any:
        d = self.to_dict()
        if key in d:
            return d[key]
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MaintenanceJob:
        """Create MaintenanceJob dynamically from mapping."""
        return _coerce_to_job(data)

    @classmethod
    def from_file(cls, filepath: str | Any) -> MaintenanceJob | list[MaintenanceJob]:
        """Load MaintenanceJob(s) dynamically from external JSON or CSV file."""
        from pathlib import Path
        from engine.file_utils import load_json_or_dict, load_dataframe_or_path

        path = Path(filepath)
        if not path.is_file():
            raise FileNotFoundError(f"Maintenance job file not found: {filepath}")
        if path.suffix.lower() == ".csv":
            df = load_dataframe_or_path(path)
            return [cls.from_dict(row.to_dict()) for _, row in df.iterrows()]
        data = load_json_or_dict(path)
        if isinstance(data, list):
            return [cls.from_dict(item) for item in data]
        return cls.from_dict(data)

    def to_file(self, filepath: str | Any) -> None:
        """Export MaintenanceJob to an external JSON configuration file."""
        import json
        from pathlib import Path

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)


@dataclass
class TechnicianAssignment:
    """Represents a technician and their single active work order assignment.

    Attributes:
        technician_id: Unique technician identifier.
        active_job_id: ID of currently active job, or None if idle.
        name: Optional technician name.
        shift_id: Optional assigned shift ID.
        interrupted_jobs: List of job IDs paused by this technician.
    """

    technician_id: str
    active_job_id: str | None = None
    name: str | None = None
    shift_id: str | None = None
    interrupted_jobs: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert technician assignment to dictionary representation."""
        return {
            "technician_id": self.technician_id,
            "active_job_id": self.active_job_id,
            "name": self.name,
            "shift_id": self.shift_id,
            "interrupted_jobs": list(self.interrupted_jobs),
        }


@dataclass(frozen=True)
class PreemptionResult:
    """Structured, deterministic decision result of preemption evaluation.

    Attributes:
        preemption_considered: Whether preemption criteria were evaluated.
        preemption_executed: Whether reassignment was actually executed.
        requires_human_approval: Whether human authorization is required before reassignment.
        technician_id: Target technician identifier.
        interrupted_job_id: Identifier of the interrupted job (None if no preemption).
        incoming_job_id: Identifier of the incoming high-priority job.
        current_priority_score: Priority score of the current job.
        incoming_priority_score: Priority score of the incoming job.
        decision_reason: Explicit explanation justifying the decision.
        interrupted_job_status: State of current job after evaluation ('interrupted', 'in_progress', etc.).
        recommended_action: Actionable recommendation for dispatchers or automated scheduler.
        status: Operational status ('executed', 'pending_approval', 'recommended', 'denied', 'no_preemption').
        safety_assessment: Structured result of data-driven safety evaluation, or None.
        interrupted_job: Copy or reference to the interrupted job instance.
        incoming_job: Copy or reference to the incoming job instance.
    """

    preemption_considered: bool
    preemption_executed: bool
    requires_human_approval: bool
    technician_id: str | None
    interrupted_job_id: str | None
    incoming_job_id: Any
    current_priority_score: float | None
    incoming_priority_score: float
    decision_reason: str
    interrupted_job_status: str | None
    recommended_action: str
    status: str
    safety_assessment: SafetyAssessmentResult | None = None
    interrupted_job: MaintenanceJob | None = None
    incoming_job: MaintenanceJob | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary representation."""
        return {
            "preemption_considered": self.preemption_considered,
            "preemption_executed": self.preemption_executed,
            "requires_human_approval": self.requires_human_approval,
            "technician_id": self.technician_id,
            "interrupted_job_id": self.interrupted_job_id,
            "incoming_job_id": self.incoming_job_id,
            "current_priority_score": self.current_priority_score,
            "incoming_priority_score": self.incoming_priority_score,
            "decision_reason": self.decision_reason,
            "interrupted_job_status": self.interrupted_job_status,
            "recommended_action": self.recommended_action,
            "status": self.status,
            "safety_assessment": self.safety_assessment.to_dict() if self.safety_assessment else None,
            "interrupted_job": self.interrupted_job.to_dict() if self.interrupted_job else None,
            "incoming_job": self.incoming_job.to_dict() if self.incoming_job else None,
        }

    def explain(self) -> str:
        """Return executive, human-readable summary of preemption decision."""
        safety_desc = self.safety_assessment.outcome if self.safety_assessment else "Not Evaluated"
        lines: list[str] = [
            "================================================================================",
            "ForgeGuard Person 2 -- Preemptive Maintenance Scheduling Decision",
            "================================================================================",
            f"Status: {self.status.upper()} | Executed: {self.preemption_executed} | "
            f"Approval Required: {self.requires_human_approval}",
            f"Safety Assessment: {safety_desc}",
            f"Technician: {self.technician_id or 'Unassigned'}",
            f"Current Job: {self.interrupted_job_id or 'None'} (Priority: {self.current_priority_score})",
            f"Incoming Job: {self.incoming_job_id} (Priority: {self.incoming_priority_score})",
            f"Decision Reason: {self.decision_reason}",
            f"Recommended Action: {self.recommended_action}",
            "================================================================================",
        ]
        return "\n".join(lines)

    def __getitem__(self, key: str) -> Any:
        d = self.to_dict()
        if key in d:
            return d[key]
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)


def _coerce_to_job(job_or_data: Any, default_prefix: str = "JOB") -> MaintenanceJob:
    """Normalize input objects, dicts, or file paths into a MaintenanceJob instance."""
    from pathlib import Path

    if isinstance(job_or_data, MaintenanceJob):
        return job_or_data
    if isinstance(job_or_data, (str, Path)):
        loaded = MaintenanceJob.from_file(job_or_data)
        return loaded[0] if isinstance(loaded, list) else loaded
    if isinstance(job_or_data, Mapping):
        job_id = job_or_data.get("job_id") or job_or_data.get("id") or f"{default_prefix}-AUTO"
        machine_id = job_or_data.get("machine_id") or job_or_data.get("machine") or job_id
        score = job_or_data.get("priority_score")
        if score is None:
            # Fallback to probability * 20.0
            prob = job_or_data.get("failure_probability", job_or_data.get("probability", 0.50))
            score = float(prob) * 20.0
        prob = job_or_data.get("failure_probability", job_or_data.get("probability"))
        return MaintenanceJob(
            job_id=job_id,
            machine_id=machine_id,
            priority_score=float(score),
            failure_probability=float(prob) if prob is not None else None,
            status=str(job_or_data.get("status", JOB_STATUS_PENDING)),
            job_type=str(job_or_data.get("job_type", "preventive_maintenance")),
            is_interruptible=job_or_data.get("is_interruptible"),
            alert_category=str(job_or_data.get("alert_category", ALERT_CATEGORY_PREDICTED_HIGH_RISK)),
            technician_id=job_or_data.get("technician_id"),
            progress=job_or_data.get("progress"),
            started_at=job_or_data.get("started_at"),
            interrupted_at=job_or_data.get("interrupted_at"),
            interruption_reason=job_or_data.get("interruption_reason"),
            preempted_by_job_id=job_or_data.get("preempted_by_job_id"),
            safety_context=job_or_data.get("safety_context"),
            metadata=dict(job_or_data.get("metadata", {})),
        )
    raise TypeError(f"Expected MaintenanceJob or mapping, got {type(job_or_data).__name__}.")


def _determine_interruptibility(
    job: MaintenanceJob, config: PreemptionConfig
) -> tuple[bool, str, SafetyAssessmentResult | None]:
    """Determines whether a job can be safely interrupted based on state, type, and safety evidence.

    Returns:
        tuple (can_interrupt: bool, reason: str, assessment: SafetyAssessmentResult | None)
    """
    safety_cfg = config.equipment_safety_config

    # 1. If explicit safety_context or equipment_safety_config is provided, perform data-driven safety assessment
    if job.safety_context is not None or safety_cfg is not None:
        ctx = job.safety_context
        if ctx is None:
            ctx = MachineTelemetryContext(machine_id=job.machine_id)
        assessment = assess_job_safety(ctx, safety_cfg)

        if assessment.outcome == OUTCOME_UNSAFE_TO_INTERRUPT:
            return (
                False,
                f"Data-driven safety assessment marked job '{job.job_id}' as UNSAFE: {assessment.explanation}",
                assessment,
            )
        if assessment.outcome == OUTCOME_INDETERMINATE:
            return (
                False,
                f"Data-driven safety assessment marked job '{job.job_id}' as INDETERMINATE: {assessment.explanation}",
                assessment,
            )

        # Outcome is SAFE_TO_INTERRUPT: verified safe by telemetry and rules
        # Still check if job is explicitly marked non-interruptible or safety-critical type
        if job.is_interruptible is False:
            return (
                False,
                f"Current job '{job.job_id}' is explicitly marked non-interruptible.",
                assessment,
            )
        if job.job_type in config.non_interruptible_job_types:
            return (
                False,
                f"Current job '{job.job_id}' type '{job.job_type}' is in non-interruptible safety list.",
                assessment,
            )
        return True, assessment.explanation, assessment

    # 2. Check explicit flag if supplied
    if job.is_interruptible is False:
        return False, f"Current job '{job.job_id}' is explicitly marked non-interruptible.", None
    if job.is_interruptible is True:
        # Still check if job type is non-interruptible for safety
        if job.job_type in config.non_interruptible_job_types:
            return (
                False,
                f"Current job '{job.job_id}' type '{job.job_type}' is in non-interruptible safety list.",
                None,
            )
        return True, "Job is explicitly marked interruptible.", None

    # 3. Check non-interruptible job types
    if job.job_type in config.non_interruptible_job_types:
        return (
            False,
            f"Current job '{job.job_id}' type '{job.job_type}' is safety-critical and cannot be paused.",
            None,
        )

    # 4. Check interruptible job types
    if job.job_type in config.interruptible_job_types:
        return True, f"Job type '{job.job_type}' is recognized as safely interruptible.", None

    # 5. Unknown interruptibility: safety fallback
    if config.allow_unknown_interruptibility:
        return True, "Unknown interruptibility permitted by configuration.", None

    return (
        False,
        f"Cannot establish interruptibility or safety for job '{job.job_id}' (type: '{job.job_type}'); "
        "missing safety metadata. Job cannot be safely interrupted.",
        None,
    )


def evaluate_preemption(
    current_job: Any,
    incoming_job: Any,
    *,
    technician_id: str | None = None,
    config: PreemptionConfig | None = None,
    approved: bool = False,
    timestamp: Any = None,
) -> PreemptionResult:
    """Evaluates whether an active job should be preempted by an incoming urgent job.

    This evaluation does NOT mutate job states. State changes occur exclusively via
    `execute_preemption()` or when authorized.

    Args:
        current_job: MaintenanceJob or dict representing currently assigned job.
        incoming_job: MaintenanceJob or dict representing incoming urgent job.
        technician_id: Optional technician ID executing the current job.
        config: PreemptionConfig instance controlling preemption thresholds and policies.
        approved: Whether human authorization has been granted.
        timestamp: Optional interruption timestamp (recorded only if provided).

    Returns:
        PreemptionResult with deterministic status, decision reasons, and recommendations.
    """
    from pathlib import Path

    if config is not None:
        if isinstance(config, (str, Path)):
            cfg = PreemptionConfig.from_file(config)
        elif isinstance(config, Mapping):
            cfg = PreemptionConfig.from_dict(config)
        elif isinstance(config, PreemptionConfig):
            cfg = config
        else:
            raise TypeError(
                f"config must be PreemptionConfig, mapping, or file path, got {type(config).__name__}."
            )
    else:
        cfg = DEFAULT_PREEMPTION_CONFIG

    cur = _coerce_to_job(current_job, "CUR")
    inc = _coerce_to_job(incoming_job, "INC")

    tech_id = technician_id or cur.technician_id

    # 1. Preemption globally enabled?
    if not cfg.enabled:
        return PreemptionResult(
            preemption_considered=True,
            preemption_executed=False,
            requires_human_approval=False,
            technician_id=tech_id,
            interrupted_job_id=cur.job_id,
            incoming_job_id=inc.job_id,
            current_priority_score=cur.priority_score,
            incoming_priority_score=inc.priority_score,
            decision_reason="Preemption is disabled in configuration.",
            interrupted_job_status=cur.status,
            recommended_action="Maintain current technician assignment.",
            status=STATUS_DENIED,
            interrupted_job=cur,
            incoming_job=inc,
        )

    # 2. Duplicate or self preemption checks
    if str(cur.job_id) == str(inc.job_id):
        return PreemptionResult(
            preemption_considered=True,
            preemption_executed=False,
            requires_human_approval=False,
            technician_id=tech_id,
            interrupted_job_id=cur.job_id,
            incoming_job_id=inc.job_id,
            current_priority_score=cur.priority_score,
            incoming_priority_score=inc.priority_score,
            decision_reason=f"Current job and incoming job refer to the same job identifier '{cur.job_id}'.",
            interrupted_job_status=cur.status,
            recommended_action="Maintain current technician assignment.",
            status=STATUS_DENIED,
            interrupted_job=cur,
            incoming_job=inc,
        )

    if cur.status in (JOB_STATUS_INTERRUPTED, JOB_STATUS_PAUSED):
        return PreemptionResult(
            preemption_considered=True,
            preemption_executed=False,
            requires_human_approval=False,
            technician_id=tech_id,
            interrupted_job_id=cur.job_id,
            incoming_job_id=inc.job_id,
            current_priority_score=cur.priority_score,
            incoming_priority_score=inc.priority_score,
            decision_reason=f"Current job '{cur.job_id}' is already interrupted; duplicate preemption rejected.",
            interrupted_job_status=cur.status,
            recommended_action="Maintain current job state; assign available technician.",
            status=STATUS_DENIED,
            interrupted_job=cur,
            incoming_job=inc,
        )

    if inc.status in (JOB_STATUS_IN_PROGRESS, JOB_STATUS_ACTIVE, JOB_STATUS_COMPLETED):
        return PreemptionResult(
            preemption_considered=True,
            preemption_executed=False,
            requires_human_approval=False,
            technician_id=tech_id,
            interrupted_job_id=cur.job_id,
            incoming_job_id=inc.job_id,
            current_priority_score=cur.priority_score,
            incoming_priority_score=inc.priority_score,
            decision_reason=f"Incoming job '{inc.job_id}' is already in status '{inc.status}'; duplicate active assignment rejected.",
            interrupted_job_status=cur.status,
            recommended_action="No preemption necessary; job already active or completed.",
            status=STATUS_DENIED,
            interrupted_job=cur,
            incoming_job=inc,
        )

    # 3. Alert Category Eligibility
    if inc.alert_category not in cfg.allowed_alert_categories:
        cat_str = inc.alert_category
        allowed_str = ", ".join(cfg.allowed_alert_categories)
        return PreemptionResult(
            preemption_considered=True,
            preemption_executed=False,
            requires_human_approval=False,
            technician_id=tech_id,
            interrupted_job_id=cur.job_id,
            incoming_job_id=inc.job_id,
            current_priority_score=cur.priority_score,
            incoming_priority_score=inc.priority_score,
            decision_reason=(
                f"Incoming job alert category '{cat_str}' is not permitted to trigger preemption. "
                f"Permitted categories: {allowed_str}."
            ),
            interrupted_job_status=cur.status,
            recommended_action="Queue incoming job in regular dispatch queue.",
            status=STATUS_DENIED,
            interrupted_job=cur,
            incoming_job=inc,
        )

    # 4. Priority Score Comparison and Delta
    if inc.priority_score <= cur.priority_score:
        return PreemptionResult(
            preemption_considered=True,
            preemption_executed=False,
            requires_human_approval=False,
            technician_id=tech_id,
            interrupted_job_id=cur.job_id,
            incoming_job_id=inc.job_id,
            current_priority_score=cur.priority_score,
            incoming_priority_score=inc.priority_score,
            decision_reason=(
                f"Incoming job priority score ({inc.priority_score:.2f}) does not exceed "
                f"current job priority score ({cur.priority_score:.2f})."
            ),
            interrupted_job_status=cur.status,
            recommended_action="Maintain current technician assignment.",
            status=STATUS_DENIED,
            interrupted_job=cur,
            incoming_job=inc,
        )

    delta = inc.priority_score - cur.priority_score
    if delta < cfg.min_priority_delta:
        return PreemptionResult(
            preemption_considered=True,
            preemption_executed=False,
            requires_human_approval=False,
            technician_id=tech_id,
            interrupted_job_id=cur.job_id,
            incoming_job_id=inc.job_id,
            current_priority_score=cur.priority_score,
            incoming_priority_score=inc.priority_score,
            decision_reason=(
                f"Priority margin ({delta:.2f}) does not meet the configured minimum priority delta "
                f"({cfg.min_priority_delta:.2f})."
            ),
            interrupted_job_status=cur.status,
            recommended_action="Maintain current technician assignment.",
            status=STATUS_DENIED,
            interrupted_job=cur,
            incoming_job=inc,
        )

    # 5. Job Status Interruptibility
    if cur.status not in cfg.interruptible_job_states:
        return PreemptionResult(
            preemption_considered=True,
            preemption_executed=False,
            requires_human_approval=False,
            technician_id=tech_id,
            interrupted_job_id=cur.job_id,
            incoming_job_id=inc.job_id,
            current_priority_score=cur.priority_score,
            incoming_priority_score=inc.priority_score,
            decision_reason=(
                f"Current job status '{cur.status}' cannot be interrupted. "
                f"Interruptible states: {list(cfg.interruptible_job_states)}."
            ),
            interrupted_job_status=cur.status,
            recommended_action="Maintain current technician assignment.",
            status=STATUS_DENIED,
            interrupted_job=cur,
            incoming_job=inc,
        )

    # 6. Safety & Work Type Interruptibility Assessment
    can_interrupt, reason, safety_res = _determine_interruptibility(cur, cfg)
    if not can_interrupt:
        priority_note = ""
        if inc.priority_score > cur.priority_score:
            priority_note = (
                f" (Incoming priority score [{inc.priority_score:.2f} > {cur.priority_score:.2f}] "
                "cannot override safety restrictions)."
            )
        return PreemptionResult(
            preemption_considered=True,
            preemption_executed=False,
            requires_human_approval=True,  # Escalate for human review
            technician_id=tech_id,
            interrupted_job_id=cur.job_id,
            incoming_job_id=inc.job_id,
            current_priority_score=cur.priority_score,
            incoming_priority_score=inc.priority_score,
            decision_reason=reason + priority_note,
            interrupted_job_status=cur.status,
            recommended_action="Preemption denied due to interruptibility safety; escalate for manual supervisor review.",
            status=STATUS_DENIED,
            safety_assessment=safety_res,
            interrupted_job=cur,
            incoming_job=inc,
        )

    # 7. Guardrail Integration & Human Approval Requirements
    requires_approval = bool(cfg.require_human_approval)

    # If guardrail config is supplied, verify if critical policies trigger mandatory review
    if cfg.guardrail_config is not None:
        if (
            cfg.guardrail_config.mandatory_review_critical
            and inc.failure_probability is not None
            and inc.failure_probability >= cfg.guardrail_config.risk_config.critical_threshold
        ):
            requires_approval = True

    # Calibrated description of incoming urgency
    if inc.alert_category == ALERT_CATEGORY_ACTUAL_FAILURE:
        urgency_desc = "Actual machine breakdown failure"
    else:
        p_str = f"prob: {inc.failure_probability:.4f}" if inc.failure_probability is not None else "critical alert"
        urgency_desc = f"Predicted high-risk failure alert ({p_str})"

    # 8. Check if approval is required but not yet granted
    if requires_approval and not approved:
        decision_reason = (
            f"Preemption criteria met: {urgency_desc} (priority {inc.priority_score:.2f}) "
            f"exceeds current job '{cur.job_id}' (priority {cur.priority_score:.2f}, delta {delta:.2f}). "
            "However, human supervisor approval is required prior to job interruption."
        )
        return PreemptionResult(
            preemption_considered=True,
            preemption_executed=False,
            requires_human_approval=True,
            technician_id=tech_id,
            interrupted_job_id=cur.job_id,
            incoming_job_id=inc.job_id,
            current_priority_score=cur.priority_score,
            incoming_priority_score=inc.priority_score,
            decision_reason=decision_reason,
            interrupted_job_status=cur.status,
            recommended_action="Preemption recommended pending human approval. Await supervisor sign-off before reassignment.",
            status=STATUS_PENDING_APPROVAL,
            safety_assessment=safety_res,
            interrupted_job=cur,
            incoming_job=inc,
        )

    # 9. All criteria met and authorized (approved or approval not required)
    decision_reason = (
        f"Preemption authorized: {urgency_desc} (priority {inc.priority_score:.2f}) "
        f"exceeds current job '{cur.job_id}' (priority {cur.priority_score:.2f}, delta {delta:.2f}). "
        f"Current job is safely interruptible."
    )
    return PreemptionResult(
        preemption_considered=True,
        preemption_executed=True,
        requires_human_approval=False,
        technician_id=tech_id,
        interrupted_job_id=cur.job_id,
        incoming_job_id=inc.job_id,
        current_priority_score=cur.priority_score,
        incoming_priority_score=inc.priority_score,
        decision_reason=decision_reason,
        interrupted_job_status=JOB_STATUS_INTERRUPTED,
        recommended_action="Safely pause current job, preserve progress state, and dispatch technician to incoming job.",
        status=STATUS_EXECUTED,
        safety_assessment=safety_res,
        interrupted_job=cur,
        incoming_job=inc,
    )


def execute_preemption(
    current_job: MaintenanceJob,
    incoming_job: MaintenanceJob,
    *,
    technician_id: str | None = None,
    config: PreemptionConfig | None = None,
    approved: bool = False,
    timestamp: Any = None,
) -> tuple[PreemptionResult, MaintenanceJob, MaintenanceJob]:
    """Executes preemption if permitted, mutating job states and preserving work progress.

    Invariants Enforced:
    - If preemption is executed:
      * current_job status becomes 'interrupted'
      * current_job progress and metadata are strictly preserved
      * incoming_job status becomes 'in_progress' and receives technician_id
    - If preemption is denied or pending approval:
      * current_job remains active and unchanged
      * incoming_job remains in its incoming status

    Args:
        current_job: The active MaintenanceJob to potentially interrupt.
        incoming_job: The incoming high-priority MaintenanceJob.
        technician_id: ID of technician to reassign.
        config: PreemptionConfig instance.
        approved: Whether human authorization has been given.
        timestamp: Optional timestamp of interruption.

    Returns:
        tuple (result: PreemptionResult, current_job: MaintenanceJob, incoming_job: MaintenanceJob)
    """
    res = evaluate_preemption(
        current_job,
        incoming_job,
        technician_id=technician_id,
        config=config,
        approved=approved,
        timestamp=timestamp,
    )

    if res.preemption_executed:
        # Safely pause current job
        current_job.status = JOB_STATUS_INTERRUPTED
        current_job.interruption_reason = res.decision_reason
        current_job.preempted_by_job_id = incoming_job.job_id
        if timestamp is not None:
            current_job.interrupted_at = timestamp

        # Dispatch incoming job
        incoming_job.status = JOB_STATUS_IN_PROGRESS
        incoming_job.technician_id = res.technician_id

    return res, current_job, incoming_job


class PreemptionManager:
    """Manages active technician assignments, evaluates preemption, and maintains reschedule queues.

    Enforces the single-active-job invariant across all managed technicians.
    """

    def __init__(self, config: PreemptionConfig | None = None) -> None:
        self.config: PreemptionConfig = config if config is not None else DEFAULT_PREEMPTION_CONFIG
        self._technicians: dict[str, TechnicianAssignment] = {}
        self._active_jobs: dict[str, MaintenanceJob] = {}  # technician_id -> MaintenanceJob
        self._reschedule_queue: list[MaintenanceJob] = []
        self._audit_history: list[PreemptionResult] = []

    def register_technician(
        self, technician_id: str, name: str | None = None, shift_id: str | None = None
    ) -> None:
        """Register a technician available for scheduling."""
        if str(technician_id).strip() == "":
            raise ValueError("technician_id cannot be empty.")
        if technician_id not in self._technicians:
            self._technicians[technician_id] = TechnicianAssignment(
                technician_id=technician_id, name=name, shift_id=shift_id
            )

    def assign_job(self, technician_id: str, job: MaintenanceJob | Mapping[str, Any]) -> MaintenanceJob:
        """Assign an active job to a technician, enforcing single-active-job invariant."""
        norm_job = _coerce_to_job(job)
        if technician_id not in self._technicians:
            self.register_technician(technician_id)

        # Enforce single active job
        if technician_id in self._active_jobs and self._active_jobs[technician_id].job_id != norm_job.job_id:
            curr = self._active_jobs[technician_id]
            raise ValueError(
                f"Technician '{technician_id}' is already actively working on job '{curr.job_id}'. "
                "Complete or interrupt the current job before assigning a new one."
            )

        norm_job.technician_id = technician_id
        norm_job.status = JOB_STATUS_IN_PROGRESS
        self._active_jobs[technician_id] = norm_job
        self._technicians[technician_id].active_job_id = str(norm_job.job_id)
        return norm_job

    def handle_incoming_alert(
        self,
        incoming_job: MaintenanceJob | Mapping[str, Any],
        technician_id: str | None = None,
        *,
        approved: bool = False,
        timestamp: Any = None,
    ) -> PreemptionResult:
        """Evaluates whether to preempt an active technician job for an incoming urgent alert.

        If technician_id is None, deterministically finds the technician on the lowest-priority
        interruptible job where preemption yields the highest priority delta.
        """
        inc = _coerce_to_job(incoming_job, "INC")

        target_tech = technician_id
        current_job: MaintenanceJob | None = None

        if target_tech is not None:
            if target_tech not in self._active_jobs:
                # Technician has no active job; assign directly without preemption
                self.assign_job(target_tech, inc)
                res = PreemptionResult(
                    preemption_considered=False,
                    preemption_executed=False,
                    requires_human_approval=False,
                    technician_id=target_tech,
                    interrupted_job_id=None,
                    incoming_job_id=inc.job_id,
                    current_priority_score=None,
                    incoming_priority_score=inc.priority_score,
                    decision_reason=f"Technician '{target_tech}' was idle; job assigned directly without preemption.",
                    interrupted_job_status=None,
                    recommended_action="Direct technician dispatch.",
                    status=STATUS_NO_PREEMPTION,
                    interrupted_job=None,
                    incoming_job=inc,
                )
                self._audit_history.append(res)
                return res
            current_job = self._active_jobs[target_tech]
        else:
            # Deterministically select best candidate: lowest priority interruptible active job
            best_candidate: tuple[float, str] | None = None
            for tech, job in self._active_jobs.items():
                if job.is_active:
                    eval_res = evaluate_preemption(
                        job, inc, technician_id=tech, config=self.config, approved=approved
                    )
                    if eval_res.status in (STATUS_EXECUTED, STATUS_PENDING_APPROVAL):
                        delta = inc.priority_score - job.priority_score
                        # Highest priority delta, broken deterministically by ascending technician_id
                        if (
                            best_candidate is None
                            or delta > best_candidate[0]
                            or (delta == best_candidate[0] and str(tech) < str(best_candidate[1]))
                        ):
                            best_candidate = (delta, tech)
                            target_tech = tech
                            current_job = job

            if target_tech is None or current_job is None:
                # No active job can be preempted
                res = PreemptionResult(
                    preemption_considered=True,
                    preemption_executed=False,
                    requires_human_approval=False,
                    technician_id=None,
                    interrupted_job_id=None,
                    incoming_job_id=inc.job_id,
                    current_priority_score=None,
                    incoming_priority_score=inc.priority_score,
                    decision_reason="No eligible interruptible active job found for preemption.",
                    interrupted_job_status=None,
                    recommended_action="Queue incoming alert in standard dispatch queue.",
                    status=STATUS_DENIED,
                    interrupted_job=None,
                    incoming_job=inc,
                )
                self._audit_history.append(res)
                return res

        # Execute or recommend preemption for target_tech and current_job
        res, cur_job, new_job = execute_preemption(
            current_job,
            inc,
            technician_id=target_tech,
            config=self.config,
            approved=approved,
            timestamp=timestamp,
        )

        if res.preemption_executed:
            # Update technician state: single active job maintained
            self._technicians[target_tech].active_job_id = str(new_job.job_id)
            self._technicians[target_tech].interrupted_jobs.append(cur_job.job_id)
            self._active_jobs[target_tech] = new_job
            # Place interrupted job in reschedule queue
            self._reschedule_queue.append(cur_job)

        self._audit_history.append(res)
        return res

    def get_reschedule_queue(self) -> list[MaintenanceJob]:
        """Return list of interrupted jobs awaiting rescheduling."""
        return list(self._reschedule_queue)

    def get_active_jobs(self) -> dict[str, MaintenanceJob]:
        """Return mapping from technician_id to their currently active job."""
        return dict(self._active_jobs)

    def get_technicians(self) -> dict[str, TechnicianAssignment]:
        """Return registered technicians."""
        return dict(self._technicians)

    def get_audit_history(self) -> list[PreemptionResult]:
        """Return list of all preemption decisions evaluated."""
        return list(self._audit_history)

    def to_dict(self) -> dict[str, Any]:
        """Convert manager state to dictionary representation."""
        return {
            "technicians": {k: v.to_dict() for k, v in self._technicians.items()},
            "active_jobs": {k: v.to_dict() for k, v in self._active_jobs.items()},
            "reschedule_queue": [j.to_dict() for j in self._reschedule_queue],
            "audit_history": [r.to_dict() for r in self._audit_history],
        }

    def explain(self) -> str:
        """Executive summary of manager status."""
        lines: list[str] = [
            "================================================================================",
            "ForgeGuard Person 2 -- Preemption Manager Status",
            "================================================================================",
            f"Registered Technicians: {len(self._technicians)} | Active Jobs: {len(self._active_jobs)} | "
            f"Reschedule Queue: {len(self._reschedule_queue)} interrupted jobs",
            "--------------------------------------------------------------------------------",
            "ACTIVE ASSIGNMENTS:",
        ]
        for tech, job in self._active_jobs.items():
            lines.append(f"  * {tech} -> Job {job.job_id} (Machine: {job.machine_id}, Priority: {job.priority_score:.2f})")
        lines.append("--------------------------------------------------------------------------------")
        if not self._reschedule_queue:
            lines.append("RESCHEDULE QUEUE: Empty (no interrupted jobs awaiting service)")
        else:
            lines.append("RESCHEDULE QUEUE (Interrupted Jobs):")
            for j in self._reschedule_queue:
                lines.append(
                    f"  ! Job {j.job_id} (Machine: {j.machine_id}, Priority: {j.priority_score:.2f}) -- "
                    f"Preempted by: {j.preempted_by_job_id}"
                )
        lines.append("================================================================================")
        return "\n".join(lines)
