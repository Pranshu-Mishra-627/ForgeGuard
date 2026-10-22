"""Deferred-Machine Risk Management for ForgeGuard Decision Engine (Person 2).

Identifies alerted machines deferred due to technician capacity constraints, ranks their
operational risk deterministically, categorizes risk tiers (Critical, High, Medium, Low),
and generates auditable follow-up escalation recommendations without silently exceeding
shift technician capacity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from engine.cost_model import CostConfig, validate_cost_config
from engine.scheduler import ScheduleResult, _resolve_id_column, plan_shift


@dataclass(frozen=True)
class RiskTierConfig:
    """Configurable risk tier thresholds and escalation parameters.

    Attributes:
        critical_threshold: Failure probability cutoff for Critical risk tier (default 0.80).
        high_threshold: Failure probability cutoff for High risk tier (default 0.60).
        medium_threshold: Failure probability cutoff for Medium risk tier (default 0.40).
        escalate_critical: Whether Critical tier alerts require active escalation (default True).
        escalate_high: Whether High tier alerts require active escalation (default True).
        escalate_medium: Whether Medium tier alerts require active escalation (default False).
        escalate_low: Whether Low tier alerts require active escalation (default False).
    """

    critical_threshold: float = 0.80
    high_threshold: float = 0.60
    medium_threshold: float = 0.40
    escalate_critical: bool = True
    escalate_high: bool = True
    escalate_medium: bool = False
    escalate_low: bool = False

    def __post_init__(self) -> None:
        """Validate risk tier thresholds."""
        for name, val in [
            ("critical_threshold", self.critical_threshold),
            ("high_threshold", self.high_threshold),
            ("medium_threshold", self.medium_threshold),
        ]:
            if isinstance(val, bool) or not isinstance(val, (int, float, np.number)):
                raise TypeError(f"'{name}' must be numeric, got {type(val).__name__}.")
            if not math.isfinite(val):
                raise ValueError(f"'{name}' must be finite, got {val}.")
            if val < 0.0 or val > 1.0:
                raise ValueError(f"'{name}' must be bounded in [0.0, 1.0], got {val}.")

        c = float(self.critical_threshold)
        h = float(self.high_threshold)
        m = float(self.medium_threshold)

        if not (c > h > m):
            raise ValueError(
                f"Risk tier thresholds must be strictly descending: critical ({c}) > high ({h}) > medium ({m})."
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert risk tier configuration to dictionary representation."""
        return {
            "critical_threshold": self.critical_threshold,
            "high_threshold": self.high_threshold,
            "medium_threshold": self.medium_threshold,
            "escalate_critical": self.escalate_critical,
            "escalate_high": self.escalate_high,
            "escalate_medium": self.escalate_medium,
            "escalate_low": self.escalate_low,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RiskTierConfig:
        """Create RiskTierConfig dynamically from mapping."""
        return cls(
            critical_threshold=float(data.get("critical_threshold", 0.80)),
            high_threshold=float(data.get("high_threshold", 0.60)),
            medium_threshold=float(data.get("medium_threshold", 0.40)),
            escalate_critical=bool(data.get("escalate_critical", True)),
            escalate_high=bool(data.get("escalate_high", True)),
            escalate_medium=bool(data.get("escalate_medium", False)),
            escalate_low=bool(data.get("escalate_low", False)),
        )

    @classmethod
    def from_file(cls, filepath: str | Path | Any) -> RiskTierConfig:
        """Load RiskTierConfig dynamically from external JSON configuration file."""
        import json

        path = Path(filepath)
        if not path.is_file():
            raise FileNotFoundError(f"Risk tier configuration file not found: {filepath}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_file(self, filepath: str | Path | Any) -> None:
        """Export RiskTierConfig to an external JSON configuration file."""
        import json

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)


DEFAULT_RISK_TIER_CONFIG = RiskTierConfig()


@dataclass(frozen=True)
class DeferredMachineRisk:
    """Structured risk profile and follow-up recommendation for a deferred machine.

    Attributes:
        machine_id: Unique machine identifier.
        failure_probability: Estimated failure probability in [0.0, 1.0].
        priority_score: Expected failure impact (probability * false_negative_cost).
        risk_tier: Qualitative risk tier ('Critical', 'High', 'Medium', 'Low').
        deferred_status: Always True for deferred machines.
        escalation_status: Operational escalation flag ('Escalated' or 'Standard Review').
        is_escalated: Boolean indicator of whether escalation review was triggered.
        recommendation: Concrete follow-up action recommendation.
        reason: Comprehensive justification explaining capacity deferral and risk tier.
        predicted_failure_mode: Machine failure mode from ML model if available.
        rank_among_deferred: 1-indexed priority ranking among deferred fleet.
    """

    machine_id: Any
    failure_probability: float
    priority_score: float
    risk_tier: str
    deferred_status: bool
    escalation_status: str
    is_escalated: bool
    recommendation: str
    reason: str
    predicted_failure_mode: str | None = None
    rank_among_deferred: int = 1

    def __post_init__(self) -> None:
        try:
            p = float(self.failure_probability)
        except (ValueError, TypeError):
            raise TypeError(f"failure_probability must be numeric, got {type(self.failure_probability).__name__}")
        if math.isnan(p) or math.isinf(p) or not (0.0 <= p <= 1.0):
            raise ValueError(f"failure_probability must be finite and in [0.0, 1.0], got {self.failure_probability}")

    def to_dict(self) -> dict[str, Any]:
        """Convert entry to dictionary representation."""
        return {
            "machine_id": self.machine_id,
            "failure_probability": self.failure_probability,
            "priority_score": self.priority_score,
            "risk_tier": self.risk_tier,
            "deferred_status": self.deferred_status,
            "escalation_status": self.escalation_status,
            "is_escalated": self.is_escalated,
            "recommendation": self.recommendation,
            "reason": self.reason,
            "rank_among_deferred": self.rank_among_deferred,
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
class DeferredRiskResult:
    """Complete deferred-machine risk assessment and escalation plan.

    Attributes:
        deferred_machines: List of DeferredMachineRisk items in descending priority order.
        risk_table: pandas DataFrame containing all deferred machines and recommendations.
        config: RiskTierConfig used for risk classification.
        total_fleet_count: Total number of machines in the evaluated fleet.
        alerted_count: Number of machines that triggered operational alert.
        selected_count: Number of alerted machines assigned to technician slots.
        deferred_count: Number of alerted machines deferred due to capacity exhaustion.
        escalated_count: Number of deferred machines triggering escalation review.
        audit_summary: Executive summary dictionary for operational leadership and UI.
    """

    deferred_machines: list[DeferredMachineRisk]
    risk_table: pd.DataFrame
    config: RiskTierConfig
    total_fleet_count: int
    alerted_count: int
    selected_count: int
    deferred_count: int
    escalated_count: int
    audit_summary: dict[str, Any]

    @property
    def table(self) -> pd.DataFrame:
        """Alias for risk_table."""
        return self.risk_table

    @property
    def deferred_risk_table(self) -> pd.DataFrame:
        """Alias for risk_table."""
        return self.risk_table

    @property
    def critical_machines(self) -> list[Any]:
        """List of deferred machine IDs in the Critical risk tier."""
        return [m.machine_id for m in self.deferred_machines if m.risk_tier == "Critical"]

    @property
    def high_risk_machines(self) -> list[Any]:
        """List of deferred machine IDs in the High risk tier."""
        return [m.machine_id for m in self.deferred_machines if m.risk_tier == "High"]

    @property
    def escalated_machines(self) -> list[Any]:
        """List of deferred machine IDs requiring active escalation."""
        return [m.machine_id for m in self.deferred_machines if m.is_escalated]

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary representation."""
        return {
            "deferred_machines": [m.to_dict() for m in self.deferred_machines],
            "risk_table": self.risk_table,
            "critical_machines": self.critical_machines,
            "high_risk_machines": self.high_risk_machines,
            "escalated_machines": self.escalated_machines,
            "total_fleet_count": self.total_fleet_count,
            "alerted_count": self.alerted_count,
            "selected_count": self.selected_count,
            "deferred_count": self.deferred_count,
            "escalated_count": self.escalated_count,
            "audit_summary": self.audit_summary,
        }

    def explain(self) -> str:
        """Returns a comprehensive, human-readable executive explanation."""
        lines = [
            "ForgeGuard Person 2 -- Deferred-Machine Risk & Escalation Report",
            "=" * 65,
            f"Fleet Overview: {self.total_fleet_count} total machines | {self.alerted_count} operational alerts",
            f"Capacity Status: {self.selected_count} dispatched | {self.deferred_count} deferred alerts ({self.escalated_count} escalated)",
        ]

        if self.deferred_count == 0:
            lines.append("-" * 65)
            lines.append("No machines deferred: All triggered alerts accommodated within technician slot capacity.")
            return "\n".join(lines)

        lines.append("-" * 65)
        lines.append(f"Ranked Deferred Machines ({self.deferred_count} total):")

        for m in self.deferred_machines:
            escalate_tag = "[ESCALATED]" if m.is_escalated else "[STANDARD]"
            mode_tag = f" ({m.predicted_failure_mode})" if m.predicted_failure_mode else ""
            lines.append(
                f"  #{m.rank_among_deferred} {m.machine_id}{mode_tag} | Tier: {m.risk_tier} {escalate_tag} | "
                f"Prob: {m.failure_probability:.4f} | Priority: {m.priority_score:.2f}"
            )
            lines.append(f"     Action: {m.recommendation}")

        lines.append("-" * 65)
        lines.append("Policy Constraints:")
        lines.append("  - Escalation recommendations provide immediate managerial awareness and parts staging;")
        lines.append("  - Technician slot limit is strictly preserved (no unbudgeted dispatching in current shift);")
        lines.append("  - Deferred machines are prioritized as candidates for subsequent shift planning.")

        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self.deferred_machines)

    def __iter__(self):
        return iter(self.deferred_machines)

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            d = self.to_dict()
            if key in d:
                return d[key]
            if hasattr(self, key):
                return getattr(self, key)
            raise KeyError(key)
        return self.deferred_machines[key]


def _classify_risk_tier(prob: float, config: RiskTierConfig) -> tuple[str, bool, str, str]:
    """Classifies risk tier and determines escalation status and recommendation.

    Probabilistic calibrated phrasing is strictly used; never claims a machine will definitely fail.
    """
    if prob >= config.critical_threshold:
        tier = "Critical"
        is_esc = config.escalate_critical
        status = "Escalated" if is_esc else "Standard Review"
        rec = (
            "Immediate supervisor review & operational risk mitigation required; "
            "inspect telemetry vibration/thermal signatures, verify safety interlocks, "
            "and consider operating load reduction."
        )
        context = (
            f"Machine exhibits critical estimated failure risk (probability {prob:.4f} >= {config.critical_threshold:.2f}). "
            "Exhausted technician capacity prevents shift service; immediate supervisor review required."
        )
    elif prob >= config.high_threshold:
        tier = "High"
        is_esc = config.escalate_high
        status = "Escalated" if is_esc else "Standard Review"
        rec = (
            "Expedited maintenance review; monitor sensor vibration and temperature trends continuously, "
            "and verify replacement part availability in inventory."
        )
        context = (
            f"Machine exhibits elevated failure risk (probability {prob:.4f} >= {config.high_threshold:.2f}). "
            "Technician capacity exhausted; expedite engineering review and monitor sensor trends."
        )
    elif prob >= config.medium_threshold:
        tier = "Medium"
        is_esc = config.escalate_medium
        status = "Escalated" if is_esc else "Standard Review"
        rec = (
            "Queue as priority candidate for evaluation in next shift planning (subject to technician availability "
            "and updated telemetry); maintain standard automated sensor monitoring."
        )
        context = (
            f"Machine exhibits moderate failure risk (probability {prob:.4f} >= {config.medium_threshold:.2f}). "
            "Deferred due to capacity; candidate for next-shift scheduling review."
        )
    else:
        tier = "Low"
        is_esc = config.escalate_low
        status = "Escalated" if is_esc else "Standard Review"
        rec = (
            "Continue standard automated condition monitoring; re-evaluate failure probability during regular shift cycles."
        )
        context = (
            f"Machine exhibits low alerted failure probability ({prob:.4f} < {config.medium_threshold:.2f}). "
            "Deferred behind higher-risk assets; continue regular condition monitoring."
        )

    return tier, is_esc, status, rec, context


def evaluate_deferred_risk(
    schedule_or_pipeline_result: Any = None,
    *,
    df: pd.DataFrame | None = None,
    probabilities: Iterable[float] | np.ndarray | pd.Series | str | None = None,
    slots: int | None = None,
    threshold: float | None = None,
    costs: CostConfig | Mapping[str, Any] | None = None,
    config: RiskTierConfig | None = None,
    id_column: str | None = None,
) -> DeferredRiskResult:
    """Evaluates risk, prioritizes follow-up, and determines escalation recommendations for deferred machines.

    Accepts a ScheduleResult, PipelineResult, or direct fleet scheduling parameters.
    Guarantees:
    - Only machines that triggered the alert but were not dispatched due to capacity are evaluated.
    - Non-alerted machines are never classified as deferred.
    - Tie-breaking is deterministic (descending priority score, ascending alphanumeric machine ID).
    - Recommendations never silently assign extra technicians or exceed current shift capacity.
    - Deferred machines are not assumed to be automatically scheduled for the next shift.

    Args:
        schedule_or_pipeline_result: ScheduleResult, PipelineResult, or schedule DataFrame.
        df: Optional fleet DataFrame if scheduling directly.
        probabilities: Predicted failure probabilities or column name.
        slots: Technician slot capacity.
        threshold: Operational alert threshold.
        costs: Cost assumptions (CostConfig or dict).
        config: Optional RiskTierConfig instance.
        id_column: Name of machine ID column.

    Returns:
        DeferredRiskResult with ranked deferred machines, structured risk table, and audit metrics.

    Raises:
        TypeError: If inputs or configurations have invalid types.
        ValueError: If input parameters or probabilities are invalid.
    """
    if config is not None:
        if isinstance(config, (str, Path)):
            tier_config = RiskTierConfig.from_file(config)
        elif isinstance(config, Mapping):
            tier_config = RiskTierConfig.from_dict(config)
        elif isinstance(config, RiskTierConfig):
            tier_config = config
        else:
            raise TypeError(
                f"config must be a RiskTierConfig instance, mapping, or file path, got {type(config).__name__}."
            )
    else:
        tier_config = DEFAULT_RISK_TIER_CONFIG

    from engine.file_utils import load_dataframe_or_path

    if df is not None and isinstance(df, (str, Path)):
        df = load_dataframe_or_path(df)

    sched_res: ScheduleResult | None = None
    pred_failure_modes: dict[Any, str] = {}
    source_df: pd.DataFrame | None = None

    # 1. Resolve inputs
    if schedule_or_pipeline_result is not None:
        if isinstance(schedule_or_pipeline_result, Path) or (
            isinstance(schedule_or_pipeline_result, str)
            and (Path(schedule_or_pipeline_result).is_file() or any(schedule_or_pipeline_result.lower().endswith(ext) for ext in (".csv", ".json", ".parquet", ".pq")))
        ):
            schedule_or_pipeline_result = load_dataframe_or_path(schedule_or_pipeline_result)

        if isinstance(schedule_or_pipeline_result, ScheduleResult):
            sched_res = schedule_or_pipeline_result
        elif hasattr(schedule_or_pipeline_result, "schedule_result") and isinstance(
            schedule_or_pipeline_result.schedule_result, ScheduleResult
        ):
            # PipelineResult
            sched_res = schedule_or_pipeline_result.schedule_result
            if hasattr(schedule_or_pipeline_result, "combined_table"):
                source_df = schedule_or_pipeline_result.combined_table
        elif isinstance(schedule_or_pipeline_result, pd.DataFrame):
            source_df = schedule_or_pipeline_result
        else:
            raise TypeError(
                f"schedule_or_pipeline_result must be a ScheduleResult, PipelineResult, or DataFrame, "
                f"got {type(schedule_or_pipeline_result).__name__}."
            )

    if sched_res is None:
        if df is not None:
            if slots is None or threshold is None:
                raise ValueError("When providing 'df', 'slots' and 'threshold' must also be specified.")
            sched_res = plan_shift(
                df=df,
                probabilities=probabilities,
                slots=slots,
                threshold=threshold,
                costs=costs,
                id_column=id_column,
            )
            source_df = df
        elif source_df is not None:
            # Table passed directly; validate required columns
            req = {"machine_id", "failure_probability", "alert", "selected_for_service", "priority_score", "reason"}
            missing = req - set(source_df.columns)
            if missing:
                raise ValueError(f"Input DataFrame missing required scheduler columns: {sorted(missing)}.")
            for p in source_df["failure_probability"]:
                try:
                    fp = float(p)
                except (ValueError, TypeError):
                    raise TypeError(f"failure_probability must be numeric, got {type(p).__name__}.")
                if math.isnan(fp) or math.isinf(fp) or not (0.0 <= fp <= 1.0):
                    raise ValueError(f"failure_probability must be finite and in [0.0, 1.0], got {p}.")
        else:
            raise ValueError(
                "Must provide either a ScheduleResult, PipelineResult, DataFrame, or (df, slots, threshold)."
            )

    # 2. Extract failure modes if present in source_df
    if source_df is not None and "predicted_failure_mode" in source_df.columns:
        id_col = "machine_id" if "machine_id" in source_df.columns else source_df.columns[0]
        for _, row in source_df.iterrows():
            pred_failure_modes[row[id_col]] = str(row["predicted_failure_mode"])

    # 3. Extract and filter records
    if sched_res is not None:
        tbl = sched_res.schedule_table
        total_fleet = len(tbl)
        # Identify genuine alerts
        alert_rows = tbl[tbl["alert"] == True]
        alert_count = len(alert_rows)
        # Identify selected machines
        selected_rows = tbl[tbl["selected_for_service"] == True]
        selected_count = len(selected_rows)

        # A deferred machine MUST have triggered operational alert AND NOT received a slot
        deferred_rows = tbl[(tbl["alert"] == True) & (tbl["selected_for_service"] == False)].copy()
    else:
        # Extracted directly from source_df
        total_fleet = len(source_df)
        alert_rows = source_df[source_df["alert"] == True]
        alert_count = len(alert_rows)
        selected_rows = source_df[source_df["selected_for_service"] == True]
        selected_count = len(selected_rows)
        deferred_rows = source_df[(source_df["alert"] == True) & (source_df["selected_for_service"] == False)].copy()

    deferred_count = len(deferred_rows)

    if deferred_count == 0:
        # No deferred machines; return clean empty structured result
        empty_df = pd.DataFrame(
            columns=[
                "machine_id",
                "failure_probability",
                "priority_score",
                "risk_tier",
                "deferred_status",
                "escalation_status",
                "is_escalated",
                "recommendation",
                "reason",
                "rank_among_deferred",
                "predicted_failure_mode",
            ]
        )
        audit_summary = {
            "total_fleet_count": total_fleet,
            "alerted_count": alert_count,
            "selected_count": selected_count,
            "deferred_count": 0,
            "escalated_count": 0,
            "critical_count": 0,
            "high_risk_count": 0,
            "medium_risk_count": 0,
            "low_risk_count": 0,
            "escalation_rate_pct": 0.0,
        }
        return DeferredRiskResult(
            deferred_machines=[],
            risk_table=empty_df,
            config=tier_config,
            total_fleet_count=total_fleet,
            alerted_count=alert_count,
            selected_count=selected_count,
            deferred_count=0,
            escalated_count=0,
            audit_summary=audit_summary,
        )

    # 4. Rank deferred machines deterministically
    # Primary: descending priority_score (or descending failure_probability); Secondary: ascending alphanumeric machine_id
    def deferred_sort_key(row_tuple: Any) -> tuple[float, str]:
        # -priority_score for descending; string machine_id for ascending tie-breaking
        return (-float(row_tuple.priority_score), str(row_tuple.machine_id))

    sorted_records = sorted(deferred_rows.itertuples(index=False), key=deferred_sort_key)

    deferred_machine_items: list[DeferredMachineRisk] = []
    table_rows: list[dict[str, Any]] = []
    tier_counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    escalated_count = 0

    for rank_idx, r in enumerate(sorted_records, start=1):
        mid = getattr(r, "machine_id")
        prob = float(getattr(r, "failure_probability"))
        score = float(getattr(r, "priority_score"))
        base_reason = str(getattr(r, "reason", ""))

        mode = pred_failure_modes.get(mid)
        if mode is None and hasattr(r, "predicted_failure_mode"):
            mode = getattr(r, "predicted_failure_mode")

        tier, is_esc, esc_status, rec, context = _classify_risk_tier(prob, tier_config)
        tier_counts[tier] += 1
        if is_esc:
            escalated_count += 1

        full_reason = f"{base_reason} | Risk Assessment: {context}"

        item = DeferredMachineRisk(
            machine_id=mid,
            failure_probability=prob,
            priority_score=score,
            risk_tier=tier,
            deferred_status=True,
            escalation_status=esc_status,
            is_escalated=is_esc,
            recommendation=rec,
            reason=full_reason,
            predicted_failure_mode=mode,
            rank_among_deferred=rank_idx,
        )
        deferred_machine_items.append(item)
        table_rows.append(item.to_dict())

    risk_table_df = pd.DataFrame(table_rows)

    escalation_rate = float((escalated_count / deferred_count * 100.0) if deferred_count > 0 else 0.0)
    audit_summary = {
        "total_fleet_count": total_fleet,
        "alerted_count": alert_count,
        "selected_count": selected_count,
        "deferred_count": deferred_count,
        "escalated_count": escalated_count,
        "critical_count": tier_counts["Critical"],
        "high_risk_count": tier_counts["High"],
        "medium_risk_count": tier_counts["Medium"],
        "low_risk_count": tier_counts["Low"],
        "escalation_rate_pct": round(escalation_rate, 2),
    }

    return DeferredRiskResult(
        deferred_machines=deferred_machine_items,
        risk_table=risk_table_df,
        config=tier_config,
        total_fleet_count=total_fleet,
        alerted_count=alert_count,
        selected_count=selected_count,
        deferred_count=deferred_count,
        escalated_count=escalated_count,
        audit_summary=audit_summary,
    )


# Standard alias
manage_deferred_risk = evaluate_deferred_risk
