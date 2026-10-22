"""Shift scheduler for maintenance alert dispatching and capacity allocation.

Ranks alerted machines by expected failure impact (probability * false_negative_cost)
and allocates available technician slots deterministically under capacity constraints.

Tie-Breaking Rule:
    When multiple alerted machines have identical priority scores, ties are broken
    deterministically using the machine identifier sorted in ascending alphanumeric
    order (e.g., 'M-001' before 'M-002'). This provides an auditable, reproducible
    dispatch sequence without arbitrary random choices.

Decision Rules:
    1. Alert Eligibility: A machine triggers an alert if failure_probability >= threshold.
    2. Priority Scoring: priority_score = failure_probability * false_negative_cost.
    3. Capacity Allocation: Technicians are assigned to at most `slots` highest-priority alerts.
    4. Safety & Integrity: Non-alerted machines are never dispatched. Unused technician slots
       remain unassigned when fewer alerts exist than slots.
    5. Auditability: Every machine receives an explicit explanation justifying whether it was
       selected, deferred due to limited slots, or not alerted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from engine.cost_model import CostConfig, validate_cost_config


@dataclass(frozen=True)
class ScheduleResult:
    """Structured result returned by plan_shift.

    Attributes:
        selected_machines: List of machine identifiers selected for service (in priority order).
        deferred_machines: List of alerted machine identifiers deferred due to technician capacity constraints.
        alert_status: Mapping from machine identifier to boolean alert trigger status.
        selection_reasons: Mapping from machine identifier to explicit decision explanation string.
        schedule_table: Complete pandas DataFrame containing all machines, probabilities, alerts,
                        priority scores, dispatch selections, and reasons.
        unalerted_machines: List of machine identifiers that did not trigger an alert.
        audit_summary: Structured dictionary summarizing capacity, costs, counts, and threshold.
    """

    selected_machines: list[Any]
    deferred_machines: list[Any]
    alert_status: dict[Any, bool]
    selection_reasons: dict[Any, str]
    schedule_table: pd.DataFrame
    unalerted_machines: list[Any] = field(default_factory=list)
    audit_summary: dict[str, Any] = field(default_factory=dict)

    @property
    def table(self) -> pd.DataFrame:
        """Alias for schedule_table."""
        return self.schedule_table

    @property
    def result_table(self) -> pd.DataFrame:
        """Alias for schedule_table."""
        return self.schedule_table

    def to_dict(self) -> dict[str, Any]:
        """Convert schedule result to dictionary representation."""
        return {
            "selected_machines": self.selected_machines,
            "deferred_machines": self.deferred_machines,
            "unalerted_machines": self.unalerted_machines,
            "alert_status": self.alert_status,
            "selection_reasons": self.selection_reasons,
            "schedule_table": self.schedule_table,
            "audit_summary": self.audit_summary,
        }

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            if hasattr(self, key):
                return getattr(self, key)
            raise KeyError(key)
        fields = (
            self.selected_machines,
            self.deferred_machines,
            self.alert_status,
            self.selection_reasons,
            self.schedule_table,
            self.unalerted_machines,
            self.audit_summary,
        )
        return fields[key]

    def __iter__(self):
        # 5 items for backward compatibility:
        # sel, defr, alerts, reasons, tbl = plan_shift(...)
        return iter((
            self.selected_machines,
            self.deferred_machines,
            self.alert_status,
            self.selection_reasons,
            self.schedule_table,
        ))


def _resolve_id_column(df: pd.DataFrame, id_column: str | None) -> str:
    """Identifies and validates the machine identifier column in the DataFrame."""
    if id_column is not None:
        if id_column not in df.columns:
            raise ValueError(
                f"Specified id_column '{id_column}' not found in DataFrame columns: {list(df.columns)}."
            )
        return id_column

    candidate_names = ["machine_id", "id", "Machine_ID", "machineId", "machine"]
    for name in candidate_names:
        if name in df.columns:
            return name

    if len(df.columns) == 1:
        return df.columns[0]

    raise ValueError(
        f"Could not automatically detect machine identifier column in DataFrame with columns: {list(df.columns)}. "
        "Please provide a column named 'machine_id' or specify the 'id_column' argument."
    )


def plan_shift(
    df: pd.DataFrame,
    probabilities: Iterable[float] | np.ndarray | pd.Series | str | None,
    slots: int,
    threshold: float,
    costs: CostConfig | Mapping[str, Any] | None = None,
    id_column: str | None = None,
) -> ScheduleResult:
    """Plans a maintenance shift by selecting high-priority alerted machines within slot capacity.

    Args:
        df: pandas DataFrame containing machine records and a stable machine identifier column.
        probabilities: Predicted failure probabilities (one per machine), or column name in `df`.
        slots: Non-negative integer number of technician slots available for the shift.
        threshold: Alert threshold in [0.0, 1.0]. Machines with probability >= threshold alert.
        costs: Configurable cost assumptions (CostConfig or dict). Defaults to FN=20, FP=1.
        id_column: Optional name of column in `df` representing machine identifiers.
            Auto-detected if None ('machine_id' preferred).

    Returns:
        ScheduleResult dataclass containing:
            - selected_machines: list of machine IDs selected for service.
            - deferred_machines: list of alerted machine IDs deferred due to capacity.
            - alert_status: dict mapping machine ID to alert boolean.
            - selection_reasons: dict mapping machine ID to decision explanation string.
            - schedule_table: pandas DataFrame with columns ['machine_id', 'failure_probability',
                              'alert', 'priority_score', 'selected_for_service', 'reason'].

    Raises:
        TypeError: If input types for df, slots, or threshold are invalid.
        ValueError: If df is empty, lengths mismatch, IDs are missing or duplicate,
            slots is negative, or probabilities/thresholds are outside [0.0, 1.0] or non-finite.
    """
    # 1. Validate DataFrame
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"df must be a pandas DataFrame, got {type(df).__name__}.")

    n_machines = len(df)
    if n_machines == 0:
        raise ValueError("Input DataFrame df cannot be empty.")

    target_id_col = _resolve_id_column(df, id_column)
    id_series = df[target_id_col]

    # Validate missing identifiers
    if id_series.isna().any():
        raise ValueError("Machine identifiers contain missing or null values.")

    # Validate empty string identifiers
    str_ids = id_series.astype(str).str.strip()
    if (str_ids == "").any():
        raise ValueError("Machine identifiers contain empty values.")

    # Validate duplicate identifiers
    if id_series.duplicated().any():
        dups = id_series[id_series.duplicated()].unique().tolist()
        raise ValueError(f"Duplicate machine identifiers found in DataFrame: {dups}.")

    # 2. Extract and validate probabilities
    if isinstance(probabilities, str):
        if probabilities not in df.columns:
            raise ValueError(f"Specified probabilities column '{probabilities}' not found in DataFrame.")
        p_raw = df[probabilities]
    elif probabilities is None:
        if "failure_probability" in df.columns:
            p_raw = df["failure_probability"]
        elif "probability" in df.columns:
            p_raw = df["probability"]
        else:
            raise ValueError(
                "probabilities must be provided as an array/Series or column name in df."
            )
    else:
        p_raw = probabilities

    try:
        p_arr = np.asarray(p_raw, dtype=float)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Failed to convert probabilities to numerical float array: {exc}") from exc

    if p_arr.ndim != 1:
        raise ValueError(f"probabilities must be 1-dimensional, got {p_arr.ndim} dimensions.")

    if len(p_arr) != n_machines:
        raise ValueError(
            f"Input length mismatch: len(df)={n_machines} vs len(probabilities)={len(p_arr)}."
        )

    if not np.all(np.isfinite(p_arr)):
        raise ValueError("probabilities contains non-finite values (NaN or Inf).")

    if np.any((p_arr < 0.0) | (p_arr > 1.0)):
        raise ValueError("probabilities contains values outside the valid range [0.0, 1.0].")

    # 3. Validate slots
    if isinstance(slots, bool) or not isinstance(slots, (int, np.integer)):
        raise TypeError(f"slots must be an integer, got {type(slots).__name__}.")

    if slots < 0:
        raise ValueError(f"slots must be a non-negative integer (>= 0), got {slots}.")

    slots_int = int(slots)

    # 4. Validate threshold
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float, np.floating, np.integer)):
        raise TypeError(f"threshold must be a numeric value, got {type(threshold).__name__}.")

    if not math.isfinite(threshold):
        raise ValueError(f"threshold must be finite, got {threshold}.")

    if threshold < 0.0 or threshold > 1.0:
        raise ValueError(f"threshold must be within [0.0, 1.0], got {threshold}.")

    threshold_val = float(threshold)

    # 5. Validate costs
    cost_cfg = validate_cost_config(costs)
    fn_cost = float(cost_cfg.false_negative_cost)

    # 6. Apply Decision Rules
    # Rule 1: Alert triggered when failure_probability >= threshold
    alerts = (p_arr >= threshold_val)

    # Rule 2: Priority score = failure_probability * false_negative_cost
    priorities = p_arr * fn_cost

    # Rule 3 & 4: Rank alerted machines by descending priority score, breaking ties by ascending machine_id
    alert_indices = np.where(alerts)[0].tolist()

    def alert_ranking_key(idx: int) -> tuple[float, str]:
        # Negative priority score for descending ranking; ascending string representation of machine ID for tie-break
        return (-float(priorities[idx]), str(id_series.iloc[idx]))

    ranked_alert_indices = sorted(alert_indices, key=alert_ranking_key)
    num_alerts = len(ranked_alert_indices)

    # Rule 5, 6, 7: Assign at most `slots` technicians to highest-priority alerts
    assigned_count = min(slots_int, num_alerts)
    selected_indices_list = ranked_alert_indices[:assigned_count]
    deferred_indices_list = ranked_alert_indices[assigned_count:]

    selected_indices_set = set(selected_indices_list)

    selected_machines = [id_series.iloc[idx] for idx in selected_indices_list]
    deferred_machines = [id_series.iloc[idx] for idx in deferred_indices_list]

    # Map rank among alerted machines (1-indexed)
    alert_rank_map = {idx: rank + 1 for rank, idx in enumerate(ranked_alert_indices)}

    # Rule 8 & 9: Build explanation reasons and compile result table
    reasons: list[str] = []
    selected_for_service_flags: list[bool] = []
    alert_status_dict: dict[Any, bool] = {}
    reasons_dict: dict[Any, str] = {}

    for i in range(n_machines):
        mid = id_series.iloc[i]
        p = float(p_arr[i])
        is_alert = bool(alerts[i])
        score = float(priorities[i])
        is_selected = bool(i in selected_indices_set)

        selected_for_service_flags.append(is_selected)
        alert_status_dict[mid] = is_alert

        if is_selected:
            rank = alert_rank_map[i]
            reason = (
                f"Selected for service: Alert triggered (probability {p:.4f} >= threshold {threshold_val:.4f}); "
                f"assigned technician slot (priority score {score:.2f}, rank {rank}/{num_alerts}, {slots_int} slots available)."
            )
        elif is_alert:
            rank = alert_rank_map[i]
            if slots_int == 0:
                reason = (
                    f"Deferred: Alert triggered (probability {p:.4f} >= threshold {threshold_val:.4f}), "
                    "but zero technician slots are available."
                )
            else:
                reason = (
                    f"Deferred: Alert triggered (priority score {score:.2f}, rank {rank}/{num_alerts}), "
                    f"but technician capacity was exhausted ({slots_int} slots assigned to higher-priority alerts)."
                )
        else:
            reason = (
                f"Not alerted: Failure probability ({p:.4f}) is below alert threshold ({threshold_val:.4f})."
            )

        reasons.append(reason)
        reasons_dict[mid] = reason

    # Compile standardized result table
    result_table = pd.DataFrame(
        {
            "machine_id": id_series.values,
            "failure_probability": p_arr,
            "alert": alerts,
            "priority_score": priorities,
            "selected_for_service": selected_for_service_flags,
            "reason": reasons,
        },
        index=df.index,
    )

    # Compile unalerted machines list (clearly distinguishing all three categories)
    unalerted_machines = [id_series.iloc[i] for i in range(n_machines) if not bool(alerts[i])]

    # Compact audit summary for operations and Person 3 dashboard
    audit_summary = {
        "operational_threshold": threshold_val,
        "technician_slots": slots_int,
        "cost_assumptions": {
            "false_negative_cost": fn_cost,
            "false_positive_cost": float(cost_cfg.false_positive_cost),
        },
        "total_machines": n_machines,
        "selected_count": len(selected_machines),
        "deferred_count": len(deferred_machines),
        "unalerted_count": len(unalerted_machines),
        "capacity_utilized": len(selected_machines),
        "capacity_remaining": max(0, slots_int - len(selected_machines)),
    }

    return ScheduleResult(
        selected_machines=selected_machines,
        deferred_machines=deferred_machines,
        alert_status=alert_status_dict,
        selection_reasons=reasons_dict,
        schedule_table=result_table,
        unalerted_machines=unalerted_machines,
        audit_summary=audit_summary,
    )
