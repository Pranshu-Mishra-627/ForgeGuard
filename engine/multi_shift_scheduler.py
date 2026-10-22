"""Multi-Shift Maintenance Planner for ForgeGuard Decision Engine (Person 2).

Allocates alerted machines across sequential shifts while respecting each shift's
technician capacity. Carries deferred machines forward from earlier shifts to later
shifts, prevents duplicate assignments by default, preserves decision history,
and produces auditable multi-shift plans and utilization metrics.

Decision Rules & Scheduling Policies:
    1. Operational Alert Independence: Operational alert status (failure_probability >= threshold)
       is strictly determined by the cost-optimized threshold and never altered by shift capacity.
    2. Prioritization & Tie-Breaking: Eligible alerted machines are ranked by priority score
       (or failure probability under alternative policy), breaking ties deterministically by
       ascending alphanumeric machine ID.
    3. Carry-Forward Allocation: Unserviced alerts from Shift N carry forward as candidates
       for Shift N+1.
    4. Capacity Constraints: Each shift dispatches at most its configured technician capacity.
    5. Non-Reassignment Invariance: By default, machines assigned to Shift N are removed from
       subsequent candidate pools unless explicitly configured.
    6. Decoupled Escalation: Escalated critical-risk machines are prominently flagged but must
       not silently exceed shift technician capacity.
    7. Transparent History: Every machine receives an explicit explanation recording its shift
       assignment, prior shift deferrals, or reason for remaining unserviced.
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


@dataclass(frozen=True)
class ShiftConfig:
    """Configuration for an individual maintenance shift.

    Attributes:
        shift_id: Unique identifier for the shift (e.g. 'Shift_1', 'Morning', 'Night').
        capacity: Number of technician service slots available in this shift.
    """

    shift_id: str | int
    capacity: int

    def __post_init__(self) -> None:
        if not isinstance(self.shift_id, (str, int)) or str(self.shift_id).strip() == "":
            raise ValueError(f"shift_id must be a non-empty string or integer, got {self.shift_id!r}.")

        if isinstance(self.capacity, bool) or not isinstance(self.capacity, (int, np.integer)):
            raise TypeError(f"capacity must be an integer, got {type(self.capacity).__name__}.")

        if self.capacity < 0:
            raise ValueError(f"capacity must be a non-negative integer (>= 0), got {self.capacity}.")

    def to_dict(self) -> dict[str, Any]:
        """Convert shift configuration to dictionary representation."""
        return {
            "shift_id": self.shift_id,
            "capacity": self.capacity,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ShiftConfig:
        """Create ShiftConfig dynamically from mapping."""
        s_id = data.get("shift_id") or data.get("name") or data.get("id")
        cap = data.get("capacity") if "capacity" in data else data.get("slots")
        if s_id is None or cap is None:
            raise ValueError(f"Missing required shift fields 'shift_id' and 'capacity' in {data}.")
        return cls(shift_id=str(s_id), capacity=int(cap))

    @classmethod
    def from_file(cls, filepath: str | Path | Any) -> list[ShiftConfig] | ShiftConfig:
        """Load shift configuration(s) dynamically from an external JSON or CSV file."""
        return cls.load_shifts(filepath)

    @classmethod
    def load_shifts(
        cls, source: str | Path | Sequence[ShiftConfig | Mapping[str, Any] | Sequence[Any]]
    ) -> list[ShiftConfig]:
        """Load and normalize shifts from a file path or in-memory sequence."""
        return _normalize_shifts(source)

    @staticmethod
    def save_shifts(shifts: Sequence[ShiftConfig], filepath: str | Path | Any) -> None:
        """Export a list of ShiftConfig instances to an external JSON configuration file."""
        import json

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [s.to_dict() for s in shifts]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


@dataclass(frozen=True)
class ShiftAssignmentSummary:
    """Operational summary of capacity and dispatch decisions for a single shift.

    Attributes:
        shift_id: Identifier of the shift.
        capacity: Configured technician capacity for this shift.
        assigned_machines: List of machine identifiers assigned to this shift in priority order.
        assigned_count: Number of machines dispatched in this shift.
        unused_slots: Available technician slots remaining unassigned (capacity - assigned_count).
        utilization_rate: Capacity utilization percentage (assigned_count / capacity).
    """

    shift_id: str
    capacity: int
    assigned_machines: list[Any]
    assigned_count: int
    unused_slots: int
    utilization_rate: float

    def to_dict(self) -> dict[str, Any]:
        """Convert shift summary to dictionary representation."""
        return {
            "shift_id": self.shift_id,
            "capacity": self.capacity,
            "assigned_machines": list(self.assigned_machines),
            "assigned_count": self.assigned_count,
            "unused_slots": self.unused_slots,
            "utilization_rate": self.utilization_rate,
        }


@dataclass(frozen=True)
class MultiShiftPlanResult:
    """Structured result returned by plan_multi_shift.

    Attributes:
        shifts: Ordered list of ShiftConfig instances.
        shift_summaries: Per-shift capacity and assignment summaries.
        shift_assignments: Mapping from shift_id to list of assigned machine identifiers.
        assigned_machines: List of all machines assigned across all shifts in order of dispatch.
        still_deferred_machines: List of alerted machines remaining unserviced after the final shift.
        unalerted_machines: List of machines that did not trigger an operational alert.
        assignments_table: Consolidated pandas DataFrame with complete machine records and history.
        threshold: Operational alert threshold used for dispatch eligibility.
        ordering_policy: Scheduling policy used ('priority_score' or 'failure_probability').
        costs: CostConfig used for expected impact calculation.
        audit_summary: Executive metrics dictionary summarizing fleet counts and utilization.
    """

    shifts: list[ShiftConfig]
    shift_summaries: list[ShiftAssignmentSummary]
    shift_assignments: dict[str, list[Any]]
    assigned_machines: list[Any]
    still_deferred_machines: list[Any]
    unalerted_machines: list[Any]
    assignments_table: pd.DataFrame
    threshold: float
    ordering_policy: str
    costs: CostConfig
    audit_summary: dict[str, Any] = field(default_factory=dict)

    # Compatibility aliases with ScheduleResult
    @property
    def schedule_table(self) -> pd.DataFrame:
        """Alias for assignments_table for ScheduleResult compatibility."""
        return self.assignments_table

    @property
    def table(self) -> pd.DataFrame:
        """Alias for assignments_table."""
        return self.assignments_table

    @property
    def selected_machines(self) -> list[Any]:
        """Alias for assigned_machines for ScheduleResult compatibility."""
        return self.assigned_machines

    @property
    def deferred_machines(self) -> list[Any]:
        """Alias for still_deferred_machines for ScheduleResult compatibility."""
        return self.still_deferred_machines

    @property
    def alert_status(self) -> dict[Any, bool]:
        """Mapping from machine ID to boolean alert trigger status."""
        return dict(zip(self.assignments_table["machine_id"], self.assignments_table["alert"]))

    @property
    def selection_reasons(self) -> dict[Any, str]:
        """Mapping from machine ID to decision explanation reason."""
        return dict(zip(self.assignments_table["machine_id"], self.assignments_table["reason"]))

    @property
    def total_capacity(self) -> int:
        """Sum of technician slots across all shifts."""
        return sum(s.capacity for s in self.shifts)

    @property
    def total_assigned(self) -> int:
        """Total number of distinct machines assigned to shifts."""
        return len(self.assigned_machines)

    @property
    def total_still_deferred(self) -> int:
        """Total number of alerted machines still deferred after the final shift."""
        return len(self.still_deferred_machines)

    @property
    def total_unused_slots(self) -> int:
        """Total technician slots remaining unassigned across all shifts."""
        return sum(s.unused_slots for s in self.shift_summaries)

    @property
    def overall_capacity_utilization(self) -> float:
        """Overall fleet technician capacity utilization across all shifts."""
        tot = self.total_capacity
        return (self.total_assigned / tot) if tot > 0 else 0.0

    def get_shift(self, shift_id: str | int) -> ShiftAssignmentSummary:
        """Retrieve assignment summary for a specific shift ID."""
        str_id = str(shift_id)
        for summary in self.shift_summaries:
            if summary.shift_id == str_id:
                return summary
        raise KeyError(f"Shift ID '{shift_id}' not found in multi-shift plan.")

    def to_dict(self) -> dict[str, Any]:
        """Convert multi-shift result to dictionary representation."""
        return {
            "shifts": [s.__dict__ for s in self.shifts],
            "shift_summaries": [s.to_dict() for s in self.shift_summaries],
            "shift_assignments": {k: list(v) for k, v in self.shift_assignments.items()},
            "assigned_machines": list(self.assigned_machines),
            "still_deferred_machines": list(self.still_deferred_machines),
            "unalerted_machines": list(self.unalerted_machines),
            "assignments_table": self.assignments_table,
            "threshold": self.threshold,
            "ordering_policy": self.ordering_policy,
            "audit_summary": self.audit_summary,
        }

    def explain(self) -> str:
        """Generates an executive, human-readable summary of multi-shift dispatch decisions."""
        lines: list[str] = [
            "================================================================================",
            "ForgeGuard Person 2 -- Multi-Shift Maintenance Dispatch Plan",
            "================================================================================",
            f"Operational Threshold: {self.threshold:.4f} | Ordering Policy: {self.ordering_policy}",
            f"Fleet Total: {self.audit_summary.get('total_fleet_count', len(self.assignments_table))} machines | "
            f"Alerted: {self.audit_summary.get('alerted_count', len(self.assigned_machines) + len(self.still_deferred_machines))} | "
            f"Shifts: {len(self.shifts)} (Total Capacity: {self.total_capacity} slots)",
            f"Total Dispatched: {self.total_assigned} | Still Deferred: {self.total_still_deferred} | "
            f"Unused Slots: {self.total_unused_slots} | Utilization: {self.overall_capacity_utilization * 100:.1f}%",
            "--------------------------------------------------------------------------------",
            "SHIFT ALLOCATIONS:",
        ]

        if not self.shifts:
            lines.append("  (No shifts configured; all operational alerts are deferred)")
        else:
            for s in self.shift_summaries:
                lines.append(
                    f"  * {s.shift_id} [Capacity: {s.capacity} | Assigned: {s.assigned_count} | "
                    f"Unused: {s.unused_slots} | Utilization: {s.utilization_rate * 100:.1f}%]"
                )
                if not s.assigned_machines:
                    lines.append("      - (No machines assigned to this shift)")
                else:
                    for rank, mid in enumerate(s.assigned_machines, 1):
                        row = self.assignments_table[self.assignments_table["machine_id"] == mid].iloc[0]
                        esc_marker = "[ESCALATED] " if row.get("is_escalated", False) else ""
                        mode_str = f" | Mode: {row['predicted_failure_mode']}" if pd.notna(row.get("predicted_failure_mode")) else ""
                        lines.append(
                            f"      {rank}. {esc_marker}{mid} (prob: {row['failure_probability']:.4f}, "
                            f"priority: {row['priority_score']:.2f}, tier: {row['risk_tier']}{mode_str})"
                        )

        lines.append("--------------------------------------------------------------------------------")
        if not self.still_deferred_machines:
            lines.append("REMAINING DEFERRED ALERTS: None (all alerted machines assigned to shifts)")
        else:
            lines.append(f"REMAINING DEFERRED ALERTS ({len(self.still_deferred_machines)} unserviced due to capacity):")
            for mid in self.still_deferred_machines:
                row = self.assignments_table[self.assignments_table["machine_id"] == mid].iloc[0]
                esc_marker = "[CRITICAL ESCALATION] " if row.get("is_escalated", False) else ""
                lines.append(
                    f"  ! {esc_marker}{mid} (prob: {row['failure_probability']:.4f}, "
                    f"priority: {row['priority_score']:.2f}, tier: {row['risk_tier']}) -- {row['reason']}"
                )

        lines.append("================================================================================")
        return "\n".join(lines)

    def evaluate_guardrails(self, config: Any = None) -> Any:
        """Evaluates maintenance policy guardrails and compliance for multi-shift plan."""
        from engine.policy_guardrails import evaluate_guardrails

        return evaluate_guardrails(self, config=config)

    @property
    def guardrails(self) -> Any:
        """PolicyGuardrailResult evaluating multi-shift plan under default guardrails."""
        return self.evaluate_guardrails()

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            if hasattr(self, key):
                return getattr(self, key)
            raise KeyError(key)
        # Tuple unpacking compatibility for (selected_machines, deferred_machines, alert_status, selection_reasons, schedule_table)
        fields = (
            self.assigned_machines,
            self.still_deferred_machines,
            self.alert_status,
            self.selection_reasons,
            self.assignments_table,
        )
        return fields[key]


def _normalize_shifts(shifts: Any) -> list[ShiftConfig]:
    """Normalizes and validates flexible shift input formats into a list of ShiftConfig.

    Supported formats:
        - Sequence of ShiftConfig instances
        - Sequence of tuples: [('Shift_1', 2), ('Shift_2', 3)]
        - Sequence of dicts: [{'shift_id': 'S1', 'capacity': 2}, ...]
        - Mapping: {'Shift_1': 2, 'Shift_2': 3}
        - Sequence of integer capacities: [2, 3] (auto-assigned Shift_1, Shift_2)

    Raises:
        TypeError: If shifts or capacities have invalid types.
        ValueError: If shift capacities are negative, shift IDs are empty, or duplicate shift IDs exist.
    """
    if shifts is None:
        raise TypeError("shifts cannot be None. Provide a list of ShiftConfig, tuples, dicts, capacities, or file path.")

    if isinstance(shifts, (str, Path)):
        from engine.file_utils import load_json_or_dict, load_dataframe_or_path
        p = Path(shifts)
        if not p.is_file():
            raise FileNotFoundError(f"Shift configuration file not found: {shifts}")
        if p.suffix.lower() == ".csv":
            df_shifts = load_dataframe_or_path(p)
            s_col = "shift_id" if "shift_id" in df_shifts.columns else ("name" if "name" in df_shifts.columns else df_shifts.columns[0])
            c_col = "capacity" if "capacity" in df_shifts.columns else ("slots" if "slots" in df_shifts.columns else df_shifts.columns[1])
            shifts = [{"shift_id": row[s_col], "capacity": int(row[c_col])} for _, row in df_shifts.iterrows()]
        else:
            shifts = load_json_or_dict(p)

    norm: list[ShiftConfig] = []

    if isinstance(shifts, Mapping):
        for s_id, cap in shifts.items():
            norm.append(ShiftConfig(shift_id=str(s_id), capacity=cap))
    elif isinstance(shifts, (list, tuple)):
        for idx, item in enumerate(shifts):
            if isinstance(item, ShiftConfig):
                norm.append(item)
            elif isinstance(item, (list, tuple)):
                if len(item) != 2:
                    raise ValueError(f"Shift tuple at index {idx} must have exactly (shift_id, capacity), got {item}.")
                norm.append(ShiftConfig(shift_id=str(item[0]), capacity=item[1]))
            elif isinstance(item, Mapping):
                s_id = item.get("shift_id") or item.get("name") or item.get("id")
                cap = item.get("capacity") if "capacity" in item else item.get("slots")
                if s_id is None or cap is None:
                    raise ValueError(
                        f"Shift dict at index {idx} must contain 'shift_id' (or 'name') and 'capacity' (or 'slots'), got {item}."
                    )
                norm.append(ShiftConfig(shift_id=str(s_id), capacity=cap))
            elif isinstance(item, (int, np.integer)) and not isinstance(item, bool):
                norm.append(ShiftConfig(shift_id=f"Shift_{idx + 1}", capacity=int(item)))
            else:
                raise TypeError(
                    f"Unsupported shift item at index {idx}: {item!r} of type {type(item).__name__}."
                )
    else:
        raise TypeError(f"shifts must be a sequence or mapping of shifts, got {type(shifts).__name__}.")

    # Check for duplicate shift IDs
    seen_ids: set[str] = set()
    for s in norm:
        str_id = str(s.shift_id)
        if str_id in seen_ids:
            raise ValueError(f"Duplicate shift ID detected: '{str_id}'. All shift IDs must be unique.")
        seen_ids.add(str_id)

    return norm


def plan_multi_shift(
    schedule_or_df: Any = None,
    shifts: Any = None,
    *,
    df: pd.DataFrame | None = None,
    probabilities: Iterable[float] | np.ndarray | pd.Series | str | None = None,
    threshold: float | None = None,
    costs: CostConfig | Mapping[str, Any] | None = None,
    risk_config: RiskTierConfig | None = None,
    ordering_policy: str = "priority_score",
    allow_reassignment: bool = False,
    id_column: str | None = None,
) -> MultiShiftPlanResult:
    """Plans multi-shift capacity allocation carrying forward deferred alerts.

    Allocates alerted machines across sequential shifts while strictly enforcing shift
    capacity constraints, deterministic tie-breaking, and carry-forward deferral rules.

    Args:
        schedule_or_df: ScheduleResult, PipelineResult, fleet DataFrame, or file path (str/Path).
        shifts: Sequence, mapping, or file path of shift configurations (e.g. 'configs/shifts.json').
        df: Optional fleet DataFrame or file path if calling directly.
        probabilities: Predicted failure probabilities or column name in df.
        threshold: Operational alert threshold. If None and schedule_or_df provided,
                   uses threshold from schedule_or_df; otherwise defaults to 0.50.
        costs: CostConfig, dict, or file path with false_negative_cost and false_positive_cost.
        risk_config: Optional RiskTierConfig, dict, or file path for qualitative escalation assessment.
        ordering_policy: Ordering policy for alerted machines ('priority_score' or 'failure_probability').
        allow_reassignment: If True, permits machines assigned in earlier shifts to be
                            reassigned in later shifts. Default is False (at most one assignment).
        id_column: Name of machine ID column.

    Returns:
        MultiShiftPlanResult containing per-shift assignments, carry-forward status,
        and consolidated assignments table.

    Raises:
        TypeError: If inputs, configurations, or capacities have invalid types.
        ValueError: If input probabilities, thresholds, or shift parameters are invalid.
    """
    # 1. Normalize shifts
    if shifts is None:
        # Check if shifts was passed as second positional argument or keyword
        raise ValueError("Must provide 'shifts' parameter defining shift capacities.")
    normalized_shifts = _normalize_shifts(shifts)

    # 2. Validate ordering policy
    valid_policies = {"priority_score", "failure_probability"}
    if ordering_policy not in valid_policies:
        raise ValueError(
            f"Invalid ordering_policy: '{ordering_policy}'. Expected one of {sorted(valid_policies)}."
        )

    # 3. Resolve source inputs
    target_df: pd.DataFrame | None = None
    prob_input = probabilities
    thresh_val = threshold
    cost_input = costs
    pred_failure_modes: dict[Any, str] = {}

    if risk_config is not None:
        if isinstance(risk_config, (str, Path)):
            risk_config = RiskTierConfig.from_file(risk_config)
        elif isinstance(risk_config, Mapping):
            risk_config = RiskTierConfig.from_dict(risk_config)

    from engine.file_utils import load_dataframe_or_path

    if schedule_or_df is not None:
        if isinstance(schedule_or_df, (str, Path)):
            schedule_or_df = load_dataframe_or_path(schedule_or_df)

        if isinstance(schedule_or_df, ScheduleResult):
            target_df = schedule_or_df.schedule_table
            if thresh_val is None:
                thresh_val = schedule_or_df.audit_summary.get("operational_threshold", 0.50)
            if cost_input is None:
                cost_input = schedule_or_df.audit_summary.get("costs", None)
            if prob_input is None and "failure_probability" in target_df.columns:
                prob_input = "failure_probability"
        elif hasattr(schedule_or_df, "combined_table") and hasattr(schedule_or_df, "operational_threshold"):
            # PipelineResult
            target_df = schedule_or_df.combined_table
            if thresh_val is None:
                thresh_val = schedule_or_df.operational_threshold
            if cost_input is None:
                cost_input = schedule_or_df.costs
            if prob_input is None and "failure_probability" in target_df.columns:
                prob_input = "failure_probability"
        elif isinstance(schedule_or_df, pd.DataFrame):
            target_df = schedule_or_df
        elif isinstance(schedule_or_df, (list, tuple, Mapping)) and df is not None:
            # User passed (shifts, df=...) or similar positional mix
            normalized_shifts = _normalize_shifts(schedule_or_df)
            target_df = load_dataframe_or_path(df) if isinstance(df, (str, Path)) else df
        else:
            raise TypeError(
                f"schedule_or_df must be a ScheduleResult, PipelineResult, DataFrame, or file path, "
                f"got {type(schedule_or_df).__name__}."
            )
    elif df is not None:
        target_df = load_dataframe_or_path(df) if isinstance(df, (str, Path)) else df
    else:
        raise ValueError("Must provide either a ScheduleResult, PipelineResult, or fleet DataFrame.")

    if target_df.empty:
        raise ValueError("Input DataFrame is empty.")

    # 4. Resolve and validate machine ID column
    target_id_col = _resolve_id_column(target_df, id_column)
    id_series = target_df[target_id_col]

    if id_series.isna().any():
        raise ValueError("Machine identifiers contain missing or null values.")

    str_ids = id_series.astype(str).str.strip()
    if (str_ids == "").any():
        raise ValueError("Machine identifiers contain empty values.")

    if id_series.duplicated().any():
        dups = id_series[id_series.duplicated()].tolist()
        raise ValueError(f"Machine identifiers must be unique, found duplicates: {dups}.")

    n_machines = len(target_df)

    # 5. Resolve and validate probabilities
    if isinstance(prob_input, str):
        if prob_input not in target_df.columns:
            raise ValueError(f"Specified probabilities column '{prob_input}' not found in DataFrame.")
        p_raw = target_df[prob_input]
    elif prob_input is None:
        if "failure_probability" in target_df.columns:
            p_raw = target_df["failure_probability"]
        elif "probability" in target_df.columns:
            p_raw = target_df["probability"]
        else:
            raise ValueError("probabilities must be provided as an array/Series or column name in df.")
    else:
        p_raw = prob_input

    try:
        p_arr = np.asarray(p_raw, dtype=float)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Failed to convert probabilities to numerical float array: {exc}") from exc

    if p_arr.ndim != 1:
        raise ValueError(f"probabilities must be 1-dimensional, got {p_arr.ndim} dimensions.")

    if len(p_arr) != n_machines:
        raise ValueError(f"Input length mismatch: len(df)={n_machines} vs len(probabilities)={len(p_arr)}.")

    if not np.all(np.isfinite(p_arr)):
        raise ValueError("probabilities contains non-finite values (NaN or Inf).")

    if np.any((p_arr < 0.0) | (p_arr > 1.0)):
        raise ValueError("probabilities contains values outside valid range [0.0, 1.0].")

    # 6. Resolve and validate threshold
    if thresh_val is None:
        thresh_val = 0.50

    if isinstance(thresh_val, bool) or not isinstance(thresh_val, (int, float, np.floating, np.integer)):
        raise TypeError(f"threshold must be numeric, got {type(thresh_val).__name__}.")

    if not math.isfinite(thresh_val):
        raise ValueError(f"threshold must be finite, got {thresh_val}.")

    if thresh_val < 0.0 or thresh_val > 1.0:
        raise ValueError(f"threshold must be within [0.0, 1.0], got {thresh_val}.")

    threshold_float = float(thresh_val)

    # 7. Validate costs
    cost_cfg = validate_cost_config(cost_input)
    fn_cost = float(cost_cfg.false_negative_cost)

    # 8. Extract failure modes if present
    if "predicted_failure_mode" in target_df.columns:
        for idx in range(n_machines):
            mid = id_series.iloc[idx]
            val = target_df["predicted_failure_mode"].iloc[idx]
            if pd.notna(val):
                pred_failure_modes[mid] = str(val)

    # 9. Risk tier configuration
    tier_config = risk_config if risk_config is not None else DEFAULT_RISK_TIER_CONFIG
    if not isinstance(tier_config, RiskTierConfig):
        raise TypeError(f"risk_config must be a RiskTierConfig, got {type(tier_config).__name__}.")

    # 10. Operational Alerting & Priority Calculation
    # Alert status is strictly governed by failure_probability >= threshold
    alerts = (p_arr >= threshold_float)
    priorities = p_arr * fn_cost

    # 11. Qualitative Risk Tier Assessment per machine
    risk_tiers: list[str] = []
    is_escalated_flags: list[bool] = []
    escalation_statuses: list[str] = []
    for p in p_arr:
        tier, is_esc, status, _, _ = _classify_risk_tier(float(p), tier_config)
        risk_tiers.append(tier)
        is_escalated_flags.append(is_esc)
        escalation_statuses.append(status)

    # 12. Rank alerted machines deterministically
    alert_indices = np.where(alerts)[0].tolist()

    def sorting_key(idx: int) -> tuple[float, str]:
        if ordering_policy == "priority_score":
            primary_val = -float(priorities[idx])
        else:
            primary_val = -float(p_arr[idx])
        # Ascending alphanumeric machine ID for deterministic tie-breaking
        return (primary_val, str(id_series.iloc[idx]))

    ranked_alert_indices = sorted(alert_indices, key=sorting_key)
    overall_alert_ranks = {idx: rank + 1 for rank, idx in enumerate(ranked_alert_indices)}

    # 13. Sequential Multi-Shift Allocation with Carry-Forward
    assigned_shift_map: dict[int, str] = {}
    shift_rank_map: dict[int, int] = {}
    deferral_history_map: dict[int, list[str]] = {idx: [] for idx in range(n_machines)}

    shift_assigned_machines: dict[str, list[Any]] = {s.shift_id: [] for s in normalized_shifts}
    shift_summaries: list[ShiftAssignmentSummary] = []

    available_candidates: list[int] = list(ranked_alert_indices)
    assigned_set: set[int] = set()

    for shift in normalized_shifts:
        cap = shift.capacity
        # Dispatches up to capacity from highest-priority available candidates
        assigned_in_shift: list[int] = available_candidates[:cap]
        deferred_in_shift: list[int] = available_candidates[cap:]

        for s_rank, idx in enumerate(assigned_in_shift, 1):
            if idx not in assigned_shift_map:
                assigned_shift_map[idx] = str(shift.shift_id)
                shift_rank_map[idx] = s_rank
            shift_assigned_machines[shift.shift_id].append(id_series.iloc[idx])
            assigned_set.add(idx)

        # Deferrals in this shift
        for idx in deferred_in_shift:
            deferral_history_map[idx].append(str(shift.shift_id))

        assigned_count = len(assigned_in_shift)
        unused_slots = cap - assigned_count
        utilization = (assigned_count / cap) if cap > 0 else 0.0

        shift_summaries.append(
            ShiftAssignmentSummary(
                shift_id=str(shift.shift_id),
                capacity=cap,
                assigned_machines=list(shift_assigned_machines[shift.shift_id]),
                assigned_count=assigned_count,
                unused_slots=unused_slots,
                utilization_rate=utilization,
            )
        )

        # Carry forward: unassigned machines become candidates for subsequent shifts
        if not allow_reassignment:
            available_candidates = deferred_in_shift
        else:
            # If reassignment is enabled, keep candidates
            available_candidates = [i for i in ranked_alert_indices if i not in assigned_set]

    # 14. Determine overall assigned and still deferred
    all_assigned_machines: list[Any] = []
    for s in normalized_shifts:
        all_assigned_machines.extend(shift_assigned_machines[s.shift_id])

    still_deferred_indices = [idx for idx in ranked_alert_indices if idx not in assigned_shift_map]
    still_deferred_machines = [id_series.iloc[idx] for idx in still_deferred_indices]
    unalerted_indices = np.where(~alerts)[0].tolist()
    unalerted_machines = [id_series.iloc[idx] for idx in unalerted_indices]

    # 15. Formulate Decision Explanations
    reasons: list[str] = []
    for i in range(n_machines):
        mid = id_series.iloc[i]
        p = float(p_arr[i])
        is_alert = bool(alerts[i])
        score = float(priorities[i])
        esc_prefix = "[ESCALATION: Critical Risk] " if (is_escalated_flags[i] and is_alert) else ""

        if not is_alert:
            reason = (
                f"Not alerted (failure probability {p:.4f} < threshold {threshold_float:.4f}); "
                "no technician dispatch required."
            )
        elif i in assigned_shift_map:
            assigned_s = assigned_shift_map[i]
            s_rank = shift_rank_map[i]
            overall_rank = overall_alert_ranks[i]
            def_history = deferral_history_map[i]

            if not def_history:
                # Assigned in first shift without prior deferral
                reason = (
                    f"{esc_prefix}Assigned to {assigned_s} (rank {s_rank} in shift, "
                    f"overall alert rank {overall_rank}; priority score: {score:.2f})."
                )
            else:
                # Deferred in earlier shifts, assigned in later shift
                history_str = ", ".join(def_history)
                reason = (
                    f"{esc_prefix}Deferred in {history_str} due to technician capacity exhaustion; "
                    f"assigned to {assigned_s} (rank {s_rank} in shift, overall alert rank {overall_rank}; priority score: {score:.2f})."
                )
        else:
            # Still deferred after all shifts
            overall_rank = overall_alert_ranks[i]
            def_history = deferral_history_map[i]
            if not normalized_shifts:
                reason = (
                    f"{esc_prefix}Alert triggered (overall alert rank {overall_rank}, priority score: {score:.2f}), "
                    "but zero shifts available; machine deferred without technician assignment."
                )
            else:
                history_str = ", ".join(def_history)
                reason = (
                    f"{esc_prefix}Deferred across all shifts ({history_str}) due to technician capacity constraints; "
                    f"remaining unserviced after final shift (overall alert rank {overall_rank}; priority score: {score:.2f})."
                )
        reasons.append(reason)

    # 16. Compile Consolidated assignments_table
    table_data: dict[str, Any] = {
        "machine_id": [id_series.iloc[i] for i in range(n_machines)],
        "failure_probability": [round(float(p_arr[i]), 4) for i in range(n_machines)],
        "priority_score": [round(float(priorities[i]), 2) for i in range(n_machines)],
        "alert": [bool(alerts[i]) for i in range(n_machines)],
        "risk_tier": risk_tiers,
        "is_escalated": is_escalated_flags,
        "escalation_status": escalation_statuses,
        "assigned_shift": [assigned_shift_map.get(i, None) for i in range(n_machines)],
        "selected_for_service": [bool(i in assigned_shift_map) for i in range(n_machines)],
        "still_deferred": [bool(alerts[i] and i not in assigned_shift_map) for i in range(n_machines)],
        "overall_alert_rank": [overall_alert_ranks.get(i, None) for i in range(n_machines)],
        "shift_rank": [shift_rank_map.get(i, None) for i in range(n_machines)],
        "deferral_history": [deferral_history_map[i] for i in range(n_machines)],
        "reason": reasons,
    }

    if pred_failure_modes:
        table_data["predicted_failure_mode"] = [
            pred_failure_modes.get(id_series.iloc[i], None) for i in range(n_machines)
        ]

    assignments_df = pd.DataFrame(table_data)
    if "assigned_shift" in assignments_df.columns:
        assignments_df["assigned_shift"] = assignments_df["assigned_shift"].astype(object).where(
            assignments_df["assigned_shift"].notna(), None
        )

    # 17. Executive Audit Summary
    total_capacity = sum(s.capacity for s in normalized_shifts)
    total_assigned = len(all_assigned_machines)
    total_unused = sum(s.unused_slots for s in shift_summaries)
    overall_utilization = (total_assigned / total_capacity) if total_capacity > 0 else 0.0

    audit_summary = {
        "total_fleet_count": n_machines,
        "alerted_count": len(ranked_alert_indices),
        "total_shifts": len(normalized_shifts),
        "total_capacity": total_capacity,
        "total_assigned": total_assigned,
        "total_still_deferred": len(still_deferred_machines),
        "total_unused_slots": total_unused,
        "overall_capacity_utilization": overall_utilization,
        "threshold": threshold_float,
        "ordering_policy": ordering_policy,
        "shift_breakdown": [s.to_dict() for s in shift_summaries],
    }

    return MultiShiftPlanResult(
        shifts=normalized_shifts,
        shift_summaries=shift_summaries,
        shift_assignments=shift_assigned_machines,
        assigned_machines=all_assigned_machines,
        still_deferred_machines=still_deferred_machines,
        unalerted_machines=unalerted_machines,
        assignments_table=assignments_df,
        threshold=threshold_float,
        ordering_policy=ordering_policy,
        costs=cost_cfg,
        audit_summary=audit_summary,
    )
