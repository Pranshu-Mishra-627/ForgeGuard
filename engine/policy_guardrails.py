"""Maintenance Policy Guardrails for ForgeGuard Decision Engine (Person 2).

Evaluates operational decisions against configurable safety, compliance, and risk
guardrails without altering optimized alert thresholds or technician capacities.

Policies Evaluated:
    1. Mandatory Human Review: High-risk/critical alerts flagged for supervisor sign-off.
    2. Deferral Limit Enforcement: Flags machines deferred beyond maximum allowable consecutive shifts.
    3. Escalation for Deferred Risk: Recommends engineering escalation for unserviced critical/high-risk assets.
    4. Deterministic Precedence: Resolves multiple simultaneous policy triggers by auditable severity.
    5. Capacity Safety: Guardrails never silently create technician slots or exceed shift limits.
    6. Calibrated Probabilistic Language: Phrasing strictly avoids claiming certain failures.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from engine.cost_model import CostConfig, validate_cost_config
from engine.deferred_risk import (
    DEFAULT_RISK_TIER_CONFIG,
    RiskTierConfig,
    _classify_risk_tier,
)
from engine.scheduler import ScheduleResult, _resolve_id_column, plan_shift

# Policy Identifier Constants
POLICY_MAX_DEFERRALS_EXCEEDED = "POL_MAX_DEFERRALS_EXCEEDED"
POLICY_CRITICAL_DEFERRED = "POL_CRITICAL_DEFERRED"
POLICY_HIGH_DEFERRED = "POL_HIGH_DEFERRED"
POLICY_CRITICAL_ALERT = "POL_CRITICAL_ALERT"
POLICY_MEDIUM_DEFERRED = "POL_MEDIUM_DEFERRED"
POLICY_STANDARD_DEFERRAL = "POL_STANDARD_DEFERRAL"
POLICY_COMPLIANT = "POL_COMPLIANT"

# Violation Type Constants
VIOLATION_TYPE_POLICY_VIOLATION = "POLICY_VIOLATION"
VIOLATION_TYPE_ESCALATION_RECOMMENDED = "ESCALATION_RECOMMENDED"
VIOLATION_TYPE_MANDATORY_REVIEW = "MANDATORY_REVIEW"
VIOLATION_TYPE_NORMAL_DEFERRAL = "NORMAL_DEFERRAL"
VIOLATION_TYPE_COMPLIANT = "COMPLIANT"

# Precedence Severity Map (Higher value = higher precedence)
POLICY_SEVERITY_ORDER: dict[str, int] = {
    POLICY_MAX_DEFERRALS_EXCEEDED: 100,
    POLICY_CRITICAL_DEFERRED: 90,
    POLICY_HIGH_DEFERRED: 70,
    POLICY_CRITICAL_ALERT: 60,
    POLICY_MEDIUM_DEFERRED: 40,
    POLICY_STANDARD_DEFERRAL: 20,
    POLICY_COMPLIANT: 0,
}


@dataclass(frozen=True)
class MaintenancePolicyConfig:
    """Configurable guardrails and maintenance compliance policies.

    Attributes:
        risk_config: RiskTierConfig defining probability cutoffs for Critical, High, Medium, Low tiers.
        mandatory_review_critical: If True, all machines with failure_probability >= critical_threshold
                                   require mandatory human review.
        escalate_critical_deferred: If True, any Critical tier machine that is deferred triggers active escalation.
        escalate_high_deferred: If True, any High tier machine that is deferred triggers escalation review.
        max_consecutive_deferrals: Maximum allowable shifts a machine can be deferred before triggering a
                                   deferral violation (default: 2 shifts). Must be >= 1.
        enforce_max_deferral_violation: If True, exceeding max_consecutive_deferrals is classified as POLICY_VIOLATION.
        require_review_on_max_deferral: If True, exceeding max_consecutive_deferrals sets requires_human_review = True.
        escalate_on_max_deferral: If True, exceeding max_consecutive_deferrals sets escalation_required = True.
    """

    risk_config: RiskTierConfig = field(default_factory=RiskTierConfig)
    mandatory_review_critical: bool = True
    escalate_critical_deferred: bool = True
    escalate_high_deferred: bool = True
    max_consecutive_deferrals: int = 2
    enforce_max_deferral_violation: bool = True
    require_review_on_max_deferral: bool = True
    escalate_on_max_deferral: bool = True

    def __post_init__(self) -> None:
        """Validate guardrail configuration parameters."""
        if not isinstance(self.risk_config, RiskTierConfig):
            raise TypeError(
                f"risk_config must be a RiskTierConfig instance, got {type(self.risk_config).__name__}."
            )

        if isinstance(self.max_consecutive_deferrals, bool) or not isinstance(
            self.max_consecutive_deferrals, (int, np.integer)
        ):
            raise TypeError(
                f"max_consecutive_deferrals must be an integer, got {type(self.max_consecutive_deferrals).__name__}."
            )

        if self.max_consecutive_deferrals < 1:
            raise ValueError(
                f"max_consecutive_deferrals must be at least 1, got {self.max_consecutive_deferrals}."
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert maintenance policy configuration to dictionary representation."""
        return {
            "risk_config": self.risk_config.to_dict(),
            "mandatory_review_critical": self.mandatory_review_critical,
            "escalate_critical_deferred": self.escalate_critical_deferred,
            "escalate_high_deferred": self.escalate_high_deferred,
            "max_consecutive_deferrals": self.max_consecutive_deferrals,
            "enforce_max_deferral_violation": self.enforce_max_deferral_violation,
            "require_review_on_max_deferral": self.require_review_on_max_deferral,
            "escalate_on_max_deferral": self.escalate_on_max_deferral,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MaintenancePolicyConfig:
        """Create MaintenancePolicyConfig dynamically from mapping."""
        risk_raw = data.get("risk_config")
        if isinstance(risk_raw, RiskTierConfig):
            risk_cfg = risk_raw
        elif isinstance(risk_raw, (str, Path)):
            risk_cfg = RiskTierConfig.from_file(risk_raw)
        elif isinstance(risk_raw, Mapping):
            risk_cfg = RiskTierConfig.from_dict(risk_raw)
        else:
            risk_cfg = RiskTierConfig()

        return cls(
            risk_config=risk_cfg,
            mandatory_review_critical=bool(data.get("mandatory_review_critical", True)),
            escalate_critical_deferred=bool(data.get("escalate_critical_deferred", True)),
            escalate_high_deferred=bool(data.get("escalate_high_deferred", True)),
            max_consecutive_deferrals=int(data.get("max_consecutive_deferrals", 2)),
            enforce_max_deferral_violation=bool(data.get("enforce_max_deferral_violation", True)),
            require_review_on_max_deferral=bool(data.get("require_review_on_max_deferral", True)),
            escalate_on_max_deferral=bool(data.get("escalate_on_max_deferral", True)),
        )

    @classmethod
    def from_file(cls, filepath: str | Path | Any) -> MaintenancePolicyConfig:
        """Load MaintenancePolicyConfig dynamically from external JSON configuration file."""
        import json

        path = Path(filepath)
        if not path.is_file():
            raise FileNotFoundError(f"Maintenance policy configuration file not found: {filepath}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_file(self, filepath: str | Path | Any) -> None:
        """Export MaintenancePolicyConfig to an external JSON configuration file."""
        import json

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)


DEFAULT_POLICY_CONFIG = MaintenancePolicyConfig()


@dataclass(frozen=True)
class MachineGuardrailRecord:
    """Detailed guardrail evaluation record for an individual machine.

    Attributes:
        machine_id: Unique machine identifier.
        failure_probability: Estimated failure probability.
        priority_score: Expected failure impact (probability * false_negative_cost).
        risk_tier: Qualitative risk tier ('Critical', 'High', 'Medium', 'Low').
        alert: Operational alert status.
        selected_for_service: Whether assigned to a technician slot in any shift.
        assigned_shift: Assigned shift ID, or None if unassigned.
        still_deferred: Whether machine alerted and remains unassigned after final shift.
        consecutive_deferrals: Number of consecutive shifts machine has been deferred.
        policy_triggered: True if any guardrail was triggered.
        requires_human_review: True if human supervisor review is required.
        escalation_required: True if engineering or leadership escalation is required.
        is_violation: True if classified as a strict POLICY_VIOLATION.
        violation_type: Qualitative status ('POLICY_VIOLATION', 'ESCALATION_RECOMMENDED',
                        'MANDATORY_REVIEW', 'NORMAL_DEFERRAL', 'COMPLIANT').
        primary_policy_id: Highest precedence policy identifier triggered.
        triggered_policies: List of all policy IDs triggered for this machine in precedence order.
        policy_reason: Clear human-readable justification of guardrail determinations.
        original_reason: Decision reason from underlying scheduler.
        predicted_failure_mode: ML predicted failure mode if available.
    """

    machine_id: Any
    failure_probability: float
    priority_score: float
    risk_tier: str
    alert: bool
    selected_for_service: bool
    assigned_shift: str | None
    still_deferred: bool
    consecutive_deferrals: int
    policy_triggered: bool
    requires_human_review: bool
    escalation_required: bool
    is_violation: bool
    violation_type: str
    primary_policy_id: str
    triggered_policies: list[str]
    policy_reason: str
    original_reason: str
    predicted_failure_mode: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert machine record to dictionary representation."""
        return {
            "machine_id": self.machine_id,
            "failure_probability": self.failure_probability,
            "priority_score": self.priority_score,
            "risk_tier": self.risk_tier,
            "alert": self.alert,
            "selected_for_service": self.selected_for_service,
            "assigned_shift": self.assigned_shift,
            "still_deferred": self.still_deferred,
            "consecutive_deferrals": self.consecutive_deferrals,
            "policy_triggered": self.policy_triggered,
            "requires_human_review": self.requires_human_review,
            "escalation_required": self.escalation_required,
            "is_violation": self.is_violation,
            "violation_type": self.violation_type,
            "primary_policy_id": self.primary_policy_id,
            "triggered_policies": list(self.triggered_policies),
            "policy_reason": self.policy_reason,
            "original_reason": self.original_reason,
            "predicted_failure_mode": self.predicted_failure_mode,
        }

    def __getitem__(self, key: str) -> Any:
        d = self.to_dict()
        if key in d:
            return d[key]
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)


@dataclass(frozen=True)
class PolicyGuardrailResult:
    """Comprehensive policy guardrail audit report across all fleet machines.

    Attributes:
        records: List of MachineGuardrailRecord instances.
        guardrail_table: Consolidated pandas DataFrame with all machines and policy statuses.
        config: MaintenancePolicyConfig evaluated.
        total_fleet_count: Total machines evaluated.
        alerted_count: Machines that triggered an operational alert.
        dispatched_count: Alerted machines allocated technician slots.
        deferred_count: Alerted machines unassigned due to capacity.
        policy_triggered_count: Machines triggering at least one policy guardrail.
        human_review_count: Machines requiring mandatory human review.
        escalation_count: Machines requiring active escalation.
        violation_count: Machines triggering a strict policy violation.
        audit_summary: Executive metric dictionary for operational leadership and UI.
    """

    records: list[MachineGuardrailRecord]
    guardrail_table: pd.DataFrame
    config: MaintenancePolicyConfig
    total_fleet_count: int
    alerted_count: int
    dispatched_count: int
    deferred_count: int
    policy_triggered_count: int
    human_review_count: int
    escalation_count: int
    violation_count: int
    audit_summary: dict[str, Any] = field(default_factory=dict)

    @property
    def table(self) -> pd.DataFrame:
        """Alias for guardrail_table."""
        return self.guardrail_table

    @property
    def violations(self) -> list[Any]:
        """List of machine IDs with active policy violations."""
        return [r.machine_id for r in self.records if r.is_violation]

    @property
    def review_required_machines(self) -> list[Any]:
        """List of machine IDs requiring human review."""
        return [r.machine_id for r in self.records if r.requires_human_review]

    @property
    def escalated_machines(self) -> list[Any]:
        """List of machine IDs requiring escalation."""
        return [r.machine_id for r in self.records if r.escalation_required]

    def to_dict(self) -> dict[str, Any]:
        """Convert guardrail results to dictionary representation."""
        return {
            "records": [r.to_dict() for r in self.records],
            "guardrail_table": self.guardrail_table,
            "total_fleet_count": self.total_fleet_count,
            "alerted_count": self.alerted_count,
            "dispatched_count": self.dispatched_count,
            "deferred_count": self.deferred_count,
            "policy_triggered_count": self.policy_triggered_count,
            "human_review_count": self.human_review_count,
            "escalation_count": self.escalation_count,
            "violation_count": self.violation_count,
            "audit_summary": self.audit_summary,
        }

    def explain(self) -> str:
        """Generates an executive, human-readable summary of guardrail compliance."""
        lines: list[str] = [
            "================================================================================",
            "ForgeGuard Person 2 -- Maintenance Policy Guardrail Audit",
            "================================================================================",
            f"Fleet Total: {self.total_fleet_count} machines | Operational Alerts: {self.alerted_count}",
            f"Dispatched: {self.dispatched_count} | Deferred: {self.deferred_count}",
            f"Policy Triggers: {self.policy_triggered_count} | Violations: {self.violation_count} | "
            f"Reviews Required: {self.human_review_count} | Escalations: {self.escalation_count}",
            "--------------------------------------------------------------------------------",
        ]

        if self.violation_count > 0:
            lines.append("CRITICAL POLICY VIOLATIONS:")
            for r in self.records:
                if r.is_violation:
                    lines.append(
                        f"  [VIOLATION] Machine {r.machine_id} (prob: {r.failure_probability:.4f}, tier: {r.risk_tier}, "
                        f"deferrals: {r.consecutive_deferrals}) -- Policy: {r.primary_policy_id}\n"
                        f"              {r.policy_reason}"
                    )
            lines.append("--------------------------------------------------------------------------------")

        if self.escalation_count > 0:
            lines.append("ESCALATION RECOMMENDATIONS:")
            for r in self.records:
                if r.escalation_required and not r.is_violation:
                    lines.append(
                        f"  [ESCALATION] Machine {r.machine_id} (prob: {r.failure_probability:.4f}, tier: {r.risk_tier}) -- "
                        f"{r.policy_reason}"
                    )
            lines.append("--------------------------------------------------------------------------------")

        if self.human_review_count > 0:
            lines.append("MANDATORY HUMAN REVIEWS:")
            for r in self.records:
                if r.requires_human_review and not r.is_violation and not r.escalation_required:
                    lines.append(
                        f"  [REVIEW] Machine {r.machine_id} (prob: {r.failure_probability:.4f}, tier: {r.risk_tier}) -- "
                        f"{r.policy_reason}"
                    )
            lines.append("--------------------------------------------------------------------------------")

        if self.policy_triggered_count == 0:
            lines.append("GUARDRAIL STATUS: All operational decisions fully compliant with maintenance policies.")
            lines.append("================================================================================")
        else:
            lines.append("================================================================================")

        return "\n".join(lines)

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            if hasattr(self, key):
                return getattr(self, key)
            raise KeyError(key)
        return self.records[key]


def evaluate_guardrails(
    schedule_result_or_df: Any = None,
    *,
    df: pd.DataFrame | None = None,
    probabilities: Iterable[float] | np.ndarray | pd.Series | str | None = None,
    slots: int | None = None,
    threshold: float | None = None,
    costs: CostConfig | Mapping[str, Any] | None = None,
    config: MaintenancePolicyConfig | None = None,
    id_column: str | None = None,
) -> PolicyGuardrailResult:
    """Evaluates maintenance guardrails and compliance policies for scheduled fleets.

    Accepts a ScheduleResult, MultiShiftPlanResult, PipelineResult, or fleet DataFrame.
    Guarantees:
    - Shift technician capacity is strictly preserved; guardrails never silently create slots.
    - Deterministic precedence rule resolves simultaneous policy triggers by severity.
    - Calibrated probabilistic phrasing avoids asserting that failures are certain.
    - Historical deferrals are used when present, and never fabricated when absent.

    Args:
        schedule_result_or_df: ScheduleResult, MultiShiftPlanResult, PipelineResult, or DataFrame.
        df: Optional fleet DataFrame if calling directly.
        probabilities: Predicted failure probabilities or column name.
        slots: Technician slot capacity if calling directly.
        threshold: Operational alert threshold if calling directly.
        costs: CostConfig or dict if calling directly.
        config: MaintenancePolicyConfig defining thresholds and guardrail limits.
        id_column: Optional name of machine ID column.

    Returns:
        PolicyGuardrailResult with structured records, DataFrame, and executive summary.

    Raises:
        TypeError: If configuration or input types are invalid.
        ValueError: If input values or parameters are invalid.
    """
    if config is not None:
        if isinstance(config, (str, Path)):
            policy_cfg = MaintenancePolicyConfig.from_file(config)
        elif isinstance(config, Mapping):
            policy_cfg = MaintenancePolicyConfig.from_dict(config)
        elif isinstance(config, MaintenancePolicyConfig):
            policy_cfg = config
        else:
            raise TypeError(
                f"config must be a MaintenancePolicyConfig instance, mapping, or file path, got {type(config).__name__}."
            )
    else:
        policy_cfg = DEFAULT_POLICY_CONFIG

    from engine.file_utils import load_dataframe_or_path

    if df is not None and isinstance(df, (str, Path)):
        df = load_dataframe_or_path(df)

    # 1. Resolve source data
    source_df: pd.DataFrame | None = None
    pred_failure_modes: dict[Any, str] = {}
    total_fleet = 0

    if schedule_result_or_df is not None:
        if isinstance(schedule_result_or_df, (str, Path)):
            schedule_result_or_df = load_dataframe_or_path(schedule_result_or_df)

        if hasattr(schedule_result_or_df, "assignments_table"):
            # MultiShiftPlanResult
            source_df = schedule_result_or_df.assignments_table
        elif hasattr(schedule_result_or_df, "schedule_table"):
            # ScheduleResult
            source_df = schedule_result_or_df.schedule_table
        elif hasattr(schedule_result_or_df, "combined_table"):
            # PipelineResult
            source_df = schedule_result_or_df.combined_table
        elif isinstance(schedule_result_or_df, pd.DataFrame):
            source_df = schedule_result_or_df
        else:
            raise TypeError(
                f"schedule_result_or_df must be a ScheduleResult, MultiShiftPlanResult, PipelineResult, DataFrame, or file path, "
                f"got {type(schedule_result_or_df).__name__}."
            )
    elif df is not None:
        if slots is not None and threshold is not None:
            # Plan single shift first
            sched_res = plan_shift(
                df=df,
                probabilities=probabilities,
                slots=slots,
                threshold=threshold,
                costs=costs,
                id_column=id_column,
            )
            source_df = sched_res.schedule_table
        else:
            source_df = df
    else:
        raise ValueError("Must provide either a schedule result object or fleet DataFrame.")

    if source_df is None or source_df.empty:
        # Handle empty fleet cleanly
        empty_df = pd.DataFrame(
            columns=[
                "machine_id",
                "failure_probability",
                "priority_score",
                "risk_tier",
                "alert",
                "selected_for_service",
                "assigned_shift",
                "still_deferred",
                "consecutive_deferrals",
                "policy_triggered",
                "requires_human_review",
                "escalation_required",
                "is_violation",
                "violation_type",
                "primary_policy_id",
                "policy_reason",
                "original_reason",
                "predicted_failure_mode",
            ]
        )
        return PolicyGuardrailResult(
            records=[],
            guardrail_table=empty_df,
            config=policy_cfg,
            total_fleet_count=0,
            alerted_count=0,
            dispatched_count=0,
            deferred_count=0,
            policy_triggered_count=0,
            human_review_count=0,
            escalation_count=0,
            violation_count=0,
            audit_summary={
                "total_fleet_count": 0,
                "alerted_count": 0,
                "dispatched_count": 0,
                "deferred_count": 0,
                "policy_triggered_count": 0,
                "human_review_count": 0,
                "escalation_count": 0,
                "violation_count": 0,
            },
        )

    # 2. Validate required columns
    target_id_col = _resolve_id_column(source_df, id_column)
    id_series = source_df[target_id_col]

    if "failure_probability" not in source_df.columns and "probability" not in source_df.columns:
        raise ValueError("Input DataFrame missing required 'failure_probability' column.")

    prob_col = "failure_probability" if "failure_probability" in source_df.columns else "probability"

    # Validate probabilities
    for p in source_df[prob_col]:
        try:
            fp = float(p)
        except (ValueError, TypeError) as exc:
            raise TypeError(f"failure_probability must be numeric, got {type(p).__name__}.") from exc
        if math.isnan(fp) or math.isinf(fp) or not (0.0 <= fp <= 1.0):
            raise ValueError(f"failure_probability must be finite and in [0.0, 1.0], got {p}.")

    total_fleet = len(source_df)

    # Extract failure modes if present
    if "predicted_failure_mode" in source_df.columns:
        for idx in range(total_fleet):
            val = source_df["predicted_failure_mode"].iloc[idx]
            if pd.notna(val):
                pred_failure_modes[id_series.iloc[idx]] = str(val)

    # 3. Evaluate each machine against policy guardrails
    records: list[MachineGuardrailRecord] = []
    table_rows: list[dict[str, Any]] = []

    alerted_count = 0
    dispatched_count = 0
    deferred_count = 0
    triggered_count = 0
    review_count = 0
    escalation_count = 0
    violation_count = 0

    for idx in range(total_fleet):
        mid = id_series.iloc[idx]
        p = float(source_df[prob_col].iloc[idx])

        # Priority score
        if "priority_score" in source_df.columns:
            priority = float(source_df["priority_score"].iloc[idx])
        else:
            fn_cost = float(policy_cfg.risk_config.critical_threshold) * 20.0
            priority = p * 20.0

        # Alert status
        if "alert" in source_df.columns:
            is_alert = bool(source_df["alert"].iloc[idx])
        elif "operational_alert" in source_df.columns:
            is_alert = bool(source_df["operational_alert"].iloc[idx])
        else:
            # Fallback to threshold
            thresh = threshold if threshold is not None else 0.50
            is_alert = bool(p >= thresh)

        if is_alert:
            alerted_count += 1

        # Service / Shift dispatch status
        is_selected = False
        if "selected_for_service" in source_df.columns:
            is_selected = bool(source_df["selected_for_service"].iloc[idx])
        elif "selected" in source_df.columns:
            is_selected = bool(source_df["selected"].iloc[idx])

        assigned_shift: str | None = None
        if "assigned_shift" in source_df.columns and pd.notna(source_df["assigned_shift"].iloc[idx]):
            assigned_shift = str(source_df["assigned_shift"].iloc[idx])
            is_selected = True

        if is_selected:
            dispatched_count += 1

        # Deferral status & history
        is_deferred = bool(is_alert and not is_selected)
        if is_deferred:
            deferred_count += 1

        still_deferred = is_deferred
        if "still_deferred" in source_df.columns:
            still_deferred = bool(source_df["still_deferred"].iloc[idx])

        # Deferral count tracking
        consecutive_deferrals = 0
        if "deferral_history" in source_df.columns:
            history_val = source_df["deferral_history"].iloc[idx]
            if isinstance(history_val, (list, tuple)):
                consecutive_deferrals = len(history_val)
            elif isinstance(history_val, (int, np.integer)) and not isinstance(history_val, bool):
                consecutive_deferrals = int(history_val)
            elif is_deferred:
                consecutive_deferrals = 1
        elif is_deferred:
            # When no history is supplied, do not fabricate past deferrals: count 1 if currently deferred
            consecutive_deferrals = 1

        # Original decision explanation
        orig_reason = ""
        if "reason" in source_df.columns:
            orig_reason = str(source_df["reason"].iloc[idx])

        # Qualitative risk tier
        tier, _, _, _, _ = _classify_risk_tier(p, policy_cfg.risk_config)

        # -------------------------------------------------------------------------
        # Policy Guardrail Evaluations (Collecting all triggers)
        # -------------------------------------------------------------------------
        triggered_policies: list[str] = []
        policy_reasons: list[str] = []
        requires_review = False
        requires_escalation = False
        is_violation = False

        # Guardrail 1: Maximum Consecutive Deferral Limit
        if is_deferred and consecutive_deferrals >= policy_cfg.max_consecutive_deferrals:
            triggered_policies.append(POLICY_MAX_DEFERRALS_EXCEEDED)
            if policy_cfg.enforce_max_deferral_violation:
                is_violation = True
            if policy_cfg.require_review_on_max_deferral:
                requires_review = True
            if policy_cfg.escalate_on_max_deferral:
                requires_escalation = True
            policy_reasons.append(
                f"Consecutive deferral limit ({policy_cfg.max_consecutive_deferrals} shifts) reached or exceeded "
                f"(deferred in {consecutive_deferrals} shifts). Urgent management review required to prevent unmonitored deterioration."
            )

        # Guardrail 2: Critical Risk Deferred (Unserviced Critical Alert)
        if is_deferred and tier == "Critical":
            triggered_policies.append(POLICY_CRITICAL_DEFERRED)
            if policy_cfg.escalate_critical_deferred:
                requires_escalation = True
            requires_review = True
            is_violation = True  # Deferred critical risk is a severe policy violation
            policy_reasons.append(
                f"Critical estimated failure risk asset (prob: {p:.4f} >= {policy_cfg.risk_config.critical_threshold:.2f}) "
                "deferred due to technician capacity exhaustion. Immediate operational risk mitigation and load reduction required."
            )

        # Guardrail 3: High Risk Deferred
        elif is_deferred and tier == "High":
            triggered_policies.append(POLICY_HIGH_DEFERRED)
            if policy_cfg.escalate_high_deferred:
                requires_escalation = True
            policy_reasons.append(
                f"Elevated failure risk asset (prob: {p:.4f} >= {policy_cfg.risk_config.high_threshold:.2f}) "
                "deferred due to technician capacity constraints. Engineering escalation and continuous vibration/thermal monitoring recommended."
            )

        # Guardrail 4: Mandatory Human Review for Critical Alert (Dispatched or Deferred)
        if is_alert and tier == "Critical" and policy_cfg.mandatory_review_critical:
            triggered_policies.append(POLICY_CRITICAL_ALERT)
            requires_review = True
            if not is_deferred:
                policy_reasons.append(
                    f"Critical failure risk alert (prob: {p:.4f} >= {policy_cfg.risk_config.critical_threshold:.2f}) "
                    "requires mandatory human supervisor sign-off and verification of maintenance procedures."
                )

        # Guardrail 5: Medium Risk Deferral (Informational)
        if is_deferred and tier == "Medium" and not triggered_policies:
            triggered_policies.append(POLICY_MEDIUM_DEFERRED)
            policy_reasons.append(
                f"Moderate failure risk asset (prob: {p:.4f}) deferred behind higher-risk units; maintain standard condition monitoring."
            )

        # Standard Deferral (Low risk)
        if is_deferred and not triggered_policies:
            triggered_policies.append(POLICY_STANDARD_DEFERRAL)
            policy_reasons.append(
                f"Low-probability alert (prob: {p:.4f}) deferred due to capacity constraints; re-evaluate in subsequent shift."
            )

        # -------------------------------------------------------------------------
        # Deterministic Policy Precedence Resolution
        # -------------------------------------------------------------------------
        if not triggered_policies:
            # Compliant
            primary_policy = POLICY_COMPLIANT
            violation_type = VIOLATION_TYPE_COMPLIANT
            policy_triggered = False
            combined_reason = "Fully compliant with configured maintenance guardrails; no policy exceptions triggered."
        else:
            policy_triggered = True
            # Sort triggered policies by configured severity (highest severity first)
            triggered_policies.sort(key=lambda pol: POLICY_SEVERITY_ORDER.get(pol, 0), reverse=True)
            primary_policy = triggered_policies[0]

            # Determine violation type based on highest-precedence policy
            if is_violation or primary_policy in {POLICY_MAX_DEFERRALS_EXCEEDED, POLICY_CRITICAL_DEFERRED}:
                violation_type = VIOLATION_TYPE_POLICY_VIOLATION
                is_violation = True
            elif requires_escalation or primary_policy == POLICY_HIGH_DEFERRED:
                violation_type = VIOLATION_TYPE_ESCALATION_RECOMMENDED
            elif requires_review or primary_policy == POLICY_CRITICAL_ALERT:
                violation_type = VIOLATION_TYPE_MANDATORY_REVIEW
            elif primary_policy in {POLICY_MEDIUM_DEFERRED, POLICY_STANDARD_DEFERRAL}:
                violation_type = VIOLATION_TYPE_NORMAL_DEFERRAL
            else:
                violation_type = VIOLATION_TYPE_COMPLIANT

            combined_reason = " | ".join(policy_reasons)

        if policy_triggered:
            triggered_count += 1
        if requires_review:
            review_count += 1
        if requires_escalation:
            escalation_count += 1
        if is_violation:
            violation_count += 1

        rec = MachineGuardrailRecord(
            machine_id=mid,
            failure_probability=round(p, 4),
            priority_score=round(priority, 2),
            risk_tier=tier,
            alert=is_alert,
            selected_for_service=is_selected,
            assigned_shift=assigned_shift,
            still_deferred=still_deferred,
            consecutive_deferrals=consecutive_deferrals,
            policy_triggered=policy_triggered,
            requires_human_review=requires_review,
            escalation_required=requires_escalation,
            is_violation=is_violation,
            violation_type=violation_type,
            primary_policy_id=primary_policy,
            triggered_policies=triggered_policies,
            policy_reason=combined_reason,
            original_reason=orig_reason,
            predicted_failure_mode=pred_failure_modes.get(mid, None),
        )
        records.append(rec)
        table_rows.append(rec.to_dict())

    guardrail_df = pd.DataFrame(table_rows)

    audit_summary = {
        "total_fleet_count": total_fleet,
        "alerted_count": alerted_count,
        "dispatched_count": dispatched_count,
        "deferred_count": deferred_count,
        "policy_triggered_count": triggered_count,
        "human_review_count": review_count,
        "escalation_count": escalation_count,
        "violation_count": violation_count,
        "max_consecutive_deferrals_limit": policy_cfg.max_consecutive_deferrals,
        "mandatory_review_critical_enabled": policy_cfg.mandatory_review_critical,
        "escalate_critical_deferred_enabled": policy_cfg.escalate_critical_deferred,
        "escalate_high_deferred_enabled": policy_cfg.escalate_high_deferred,
    }

    return PolicyGuardrailResult(
        records=records,
        guardrail_table=guardrail_df,
        config=policy_cfg,
        total_fleet_count=total_fleet,
        alerted_count=alerted_count,
        dispatched_count=dispatched_count,
        deferred_count=deferred_count,
        policy_triggered_count=triggered_count,
        human_review_count=review_count,
        escalation_count=escalation_count,
        violation_count=violation_count,
        audit_summary=audit_summary,
    )
