"""Pipeline integrating Person 1's ML predictions with Person 2's Decision Engine.

Provides end-to-end integration:
1. Calls or consumes Person 1's `predict_machines(telemetry_df)`.
2. Preserves `machine_id`, `failure_probability`, and `predicted_failure_mode`.
3. Optimizes operational alert threshold on validation data using `choose_threshold()`.
4. Dispatches technician capacity and resolves priorities using `plan_shift()`.
5. Retains Person 1's `maintenance_alert` for comparison while strictly using the
   cost-selected `operational_alert` for shift scheduling.
6. Returns a combined decision table and structured `PipelineResult`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import numpy as np
import pandas as pd

from engine.cost_model import CostConfig, validate_cost_config
from engine.scheduler import ScheduleResult, _resolve_id_column, plan_shift
from engine.threshold import ThresholdResult, choose_threshold


@dataclass(frozen=True)
class PipelineResult:
    """End-to-end integration result combining ML predictions and shift planning decisions.

    Attributes:
        combined_table: Merged pandas DataFrame containing predictions, operational alerts,
                        priority scores, technician assignments, and decision reasons.
        selected_machines: List of machine identifiers selected for service in priority order.
        deferred_machines: List of alerted machine identifiers deferred due to technician capacity.
        operational_threshold: The alert threshold used for dispatch decisions.
        threshold_result: ThresholdResult from choose_threshold (if validation data was evaluated).
        schedule_result: Underlying ScheduleResult from plan_shift.
        costs: CostConfig used for threshold selection and priority scoring.
        slots: Number of technician slots allocated.
        unalerted_machines: List of machine identifiers that did not trigger an alert.
        audit_summary: Structured dictionary summarizing capacity, costs, counts, and threshold.
    """

    combined_table: pd.DataFrame
    selected_machines: list[Any]
    deferred_machines: list[Any]
    operational_threshold: float
    threshold_result: ThresholdResult | None
    schedule_result: ScheduleResult
    costs: CostConfig
    slots: int
    unalerted_machines: list[Any] = field(default_factory=list)
    audit_summary: dict[str, Any] = field(default_factory=dict)

    @property
    def schedule_table(self) -> pd.DataFrame:
        """Alias for combined_table for compatibility with ScheduleResult."""
        return self.combined_table

    @property
    def table(self) -> pd.DataFrame:
        """Alias for combined_table."""
        return self.combined_table

    @property
    def alert_status(self) -> dict[Any, bool]:
        """Mapping from machine identifier to operational alert status."""
        return self.schedule_result.alert_status

    @property
    def selection_reasons(self) -> dict[Any, str]:
        """Mapping from machine identifier to decision explanation string."""
        return self.schedule_result.selection_reasons

    @property
    def cost_curve(self) -> pd.DataFrame | None:
        """Cost curve from threshold optimization if validation data was evaluated."""
        return self.threshold_result.cost_curve if self.threshold_result else None

    @property
    def chart_data(self) -> pd.DataFrame | None:
        """Cost curve indexed by threshold for Streamlit st.line_chart() if available."""
        return self.threshold_result.chart_data if self.threshold_result else None

    @property
    def baseline_comparison(self) -> dict[str, Any] | None:
        """Baseline comparison against threshold 0.50 if validation data was evaluated."""
        return self.threshold_result.baseline_comparison if self.threshold_result else None

    @property
    def cost_difference(self) -> float | None:
        """Cost difference vs baseline 0.50 if validation data was evaluated."""
        return self.threshold_result.cost_difference if self.threshold_result else None

    @property
    def optimal_threshold(self) -> float:
        """Operational threshold selected for alerts."""
        return self.operational_threshold

    @property
    def optimal_cost(self) -> float | None:
        """Optimal minimum validation cost achieved if validation data was evaluated."""
        return self.threshold_result.optimal_cost if self.threshold_result else None

    @property
    def explanation(self) -> str:
        """Explanation of threshold optimization if available."""
        if self.threshold_result:
            return self.threshold_result.explanation
        return f"Operational threshold set to fixed value {self.operational_threshold:.2f}."

    def explain(self) -> str:
        """Returns a comprehensive, human-readable summary of the pipeline decision analysis."""
        if self.threshold_result:
            return self.threshold_result.explain()
        return (
            f"Pipeline Execution Summary:\n"
            f"  - Operational Threshold: {self.operational_threshold:.2f} (manually configured)\n"
            f"  - Fleet Machines: {len(self.combined_table)}\n"
            f"  - Selected: {len(self.selected_machines)}, Deferred: {len(self.deferred_machines)}, "
            f"Unalerted: {len(self.unalerted_machines)}"
        )

    def get_business_impact(
        self,
        monetary_value_per_unit: float | None = None,
        currency: str = "USD",
    ) -> Any:
        """Calculates executive business impact from the pipeline's threshold result."""
        if self.threshold_result is None:
            raise ValueError(
                "Cannot calculate business impact without validation threshold optimization results."
            )
        return self.threshold_result.get_business_impact(
            monetary_value_per_unit=monetary_value_per_unit,
            currency=currency,
        )

    @property
    def business_impact(self) -> Any:
        """BusinessImpactResult if threshold optimization was performed on validation data."""
        if self.threshold_result is not None:
            return self.threshold_result.business_impact
        return None

    def evaluate_deferred_risk(self, config: Any = None) -> Any:
        """Evaluates operational risk and follow-up recommendations for deferred machines."""
        from engine.deferred_risk import evaluate_deferred_risk

        return evaluate_deferred_risk(self, config=config)

    @property
    def deferred_risk(self) -> Any:
        """DeferredRiskResult evaluating deferred machines from pipeline execution."""
        return self.evaluate_deferred_risk()

    def plan_multi_shift(self, shifts: Any, **kwargs: Any) -> Any:
        """Allocates operational alerts across sequential shifts with carry-forward deferrals."""
        from engine.multi_shift_scheduler import plan_multi_shift

        return plan_multi_shift(self, shifts=shifts, **kwargs)

    def evaluate_guardrails(self, config: Any = None) -> Any:
        """Evaluates maintenance policy guardrails and compliance for pipeline results."""
        from engine.policy_guardrails import evaluate_guardrails

        return evaluate_guardrails(self, config=config)

    @property
    def guardrails(self) -> Any:
        """PolicyGuardrailResult evaluating pipeline results under default guardrails."""
        return self.evaluate_guardrails()

    def evaluate_preemption(
        self,
        incoming_job: Any,
        current_machine_id: Any = None,
        technician_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Evaluates whether to preempt an active dispatch from pipeline schedule."""
        return self.schedule_result.evaluate_preemption(
            incoming_job,
            current_machine_id=current_machine_id,
            technician_id=technician_id,
            **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert pipeline result to dictionary representation."""
        return {
            "combined_table": self.combined_table,
            "selected_machines": self.selected_machines,
            "deferred_machines": self.deferred_machines,
            "unalerted_machines": self.unalerted_machines,
            "operational_threshold": self.operational_threshold,
            "threshold_result": self.threshold_result,
            "schedule_result": self.schedule_result,
            "costs": self.costs,
            "slots": self.slots,
            "audit_summary": self.audit_summary,
        }

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            if hasattr(self, key):
                return getattr(self, key)
            raise KeyError(key)
        fields = (
            self.combined_table,
            self.selected_machines,
            self.deferred_machines,
            self.operational_threshold,
            self.threshold_result,
            self.schedule_result,
            self.costs,
            self.slots,
            self.unalerted_machines,
            self.audit_summary,
        )
        return fields[key]

    def __iter__(self):
        # 8 items for backward compatibility:
        return iter((
            self.combined_table,
            self.selected_machines,
            self.deferred_machines,
            self.operational_threshold,
            self.threshold_result,
            self.schedule_result,
            self.costs,
            self.slots,
        ))


def resolve_predict_machines(
    predict_fn: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
) -> Callable[[pd.DataFrame], pd.DataFrame]:
    """Resolves and returns the ML prediction function.

    If a callable is provided, it is validated and returned.
    Otherwise, attempts dynamic discovery across standard candidate module paths.

    Raises:
        TypeError: If predict_fn is provided but not callable.
        ImportError: If no predict_machines implementation is found in the repository.
    """
    if predict_fn is not None:
        if not callable(predict_fn):
            raise TypeError(f"predict_fn must be callable, got {type(predict_fn).__name__}.")
        return predict_fn

    candidate_modules = [
        ("predict_machines", "predict_machines"),
        ("model", "predict_machines"),
        ("ml", "predict_machines"),
        ("ml.predict", "predict_machines"),
        ("ml.model", "predict_machines"),
        ("prediction", "predict_machines"),
        ("src.model", "predict_machines"),
        ("src.predict", "predict_machines"),
    ]

    for mod_name, fn_name in candidate_modules:
        try:
            mod = __import__(mod_name, fromlist=[fn_name])
            fn = getattr(mod, fn_name, None)
            if fn is not None and callable(fn):
                return fn
        except ImportError:
            continue

    raise ImportError(
        "Person 1's ML prediction function 'predict_machines(telemetry_df)' was not found in the repository. "
        "Please provide predict_fn explicitly or ensure Person 1's module is on the Python path."
    )


def integrate_predictions(
    predictions_df: pd.DataFrame,
    y_val: Iterable[int | float | bool] | np.ndarray | pd.Series | None = None,
    p_val: Iterable[float] | np.ndarray | pd.Series | None = None,
    threshold: float | None = None,
    slots: int = 3,
    costs: CostConfig | Mapping[str, Any] | None = None,
    id_column: str | None = None,
    telemetry_df: pd.DataFrame | None = None,
) -> PipelineResult:
    """Integrates Person 1's prediction DataFrame with Person 2's decision engine.

    Args:
        predictions_df: DataFrame returned by predict_machines, containing machine_id,
            failure_probability, predicted_failure_mode, and optionally maintenance_alert.
        y_val: Validation ground-truth binary labels (0/1) for operational threshold selection.
        p_val: Validation failure probabilities corresponding to y_val.
        threshold: Explicit operational alert threshold. Used directly if provided.
            If None, y_val and p_val must be provided to select threshold via choose_threshold().
        slots: Non-negative integer number of technician slots available (default: 3).
        costs: Configurable cost assumptions (CostConfig or dict). Defaults to FN=20.0, FP=1.0.
        id_column: Optional name of machine ID column in predictions_df. Auto-detected if None.
        telemetry_df: Optional original telemetry DataFrame to preserve extra sensor/line features.

    Returns:
        PipelineResult containing the combined decision table, selected/deferred machines,
        operational threshold, threshold curve (if computed), and scheduling metadata.

    Raises:
        TypeError: If input types are invalid.
        ValueError: If predictions_df is empty, required columns are missing, probabilities
            are non-finite or out of [0, 1], or threshold cannot be determined.
    """
    if isinstance(predictions_df, Path) or (
        isinstance(predictions_df, str)
        and (Path(predictions_df).is_file() or any(predictions_df.lower().endswith(ext) for ext in (".csv", ".json", ".parquet", ".pq")))
    ):
        from engine.file_utils import load_dataframe_or_path

        predictions_df = load_dataframe_or_path(predictions_df)
    elif not isinstance(predictions_df, pd.DataFrame):
        raise TypeError(f"predictions_df must be a pandas DataFrame, got {type(predictions_df).__name__}.")

    if telemetry_df is not None and (
        isinstance(telemetry_df, Path)
        or (
            isinstance(telemetry_df, str)
            and (Path(telemetry_df).is_file() or any(telemetry_df.lower().endswith(ext) for ext in (".csv", ".json", ".parquet", ".pq")))
        )
    ):
        from engine.file_utils import load_dataframe_or_path

        telemetry_df = load_dataframe_or_path(telemetry_df)

    if len(predictions_df) == 0:
        raise ValueError("predictions_df cannot be empty.")

    target_id_col = _resolve_id_column(predictions_df, id_column)

    # Validate required columns from Person 1 contract
    if "failure_probability" not in predictions_df.columns:
        raise ValueError(
            f"predictions_df is missing required column 'failure_probability'. Columns present: {list(predictions_df.columns)}"
        )

    if "predicted_failure_mode" not in predictions_df.columns:
        raise ValueError(
            f"predictions_df is missing required column 'predicted_failure_mode'. Columns present: {list(predictions_df.columns)}"
        )

    cost_cfg = validate_cost_config(costs)

    # Determine operational threshold
    threshold_result: ThresholdResult | None = None
    if y_val is not None and p_val is not None:
        threshold_result = choose_threshold(
            y_true=y_val,
            probabilities=p_val,
            costs=cost_cfg,
        )
        operational_threshold = threshold_result.threshold
    elif threshold is not None:
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float, np.floating, np.integer)):
            raise TypeError(f"threshold must be numeric, got {type(threshold).__name__}.")
        operational_threshold = float(threshold)
        if operational_threshold < 0.0 or operational_threshold > 1.0:
            raise ValueError(f"threshold must be within [0.0, 1.0], got {operational_threshold}.")
    else:
        raise ValueError(
            "Operational threshold must be determined: provide validation data (y_val, p_val) "
            "to select the optimal threshold via choose_threshold(), or supply an explicit 'threshold' float."
        )

    # Execute shift scheduling using Person 2 scheduler
    schedule_result = plan_shift(
        df=predictions_df,
        probabilities=predictions_df["failure_probability"],
        slots=slots,
        threshold=operational_threshold,
        costs=cost_cfg,
        id_column=target_id_col,
    )

    # Build the combined table preserving all Person 1 fields and adding Person 2 decisions
    combined_table = predictions_df.copy()

    sched_tbl = schedule_result.schedule_table

    # Standardized output columns
    combined_table["operational_alert"] = [bool(x) for x in sched_tbl["alert"].values]
    combined_table["alert"] = combined_table["operational_alert"]
    combined_table["priority_score"] = sched_tbl["priority_score"].astype(float).values
    combined_table["service_assignment"] = [bool(x) for x in sched_tbl["selected_for_service"].values]
    combined_table["selected_for_service"] = combined_table["service_assignment"]
    combined_table["decision_reason"] = sched_tbl["reason"].values
    combined_table["reason"] = combined_table["decision_reason"]

    # Merge additional telemetry features from telemetry_df if provided and not already present
    if telemetry_df is not None and isinstance(telemetry_df, pd.DataFrame):
        if len(telemetry_df) == len(combined_table):
            for col in telemetry_df.columns:
                if col not in combined_table.columns:
                    combined_table[col] = telemetry_df[col].values

    # Arrange primary columns at front for readability
    primary_cols = [
        target_id_col,
        "failure_probability",
        "predicted_failure_mode",
    ]
    if "maintenance_alert" in combined_table.columns:
        primary_cols.append("maintenance_alert")

    decision_cols = [
        "operational_alert",
        "priority_score",
        "service_assignment",
        "decision_reason",
    ]
    alias_cols = ["alert", "selected_for_service", "reason"]
    remaining_cols = [c for c in combined_table.columns if c not in primary_cols + decision_cols + alias_cols]

    ordered_columns = primary_cols + decision_cols + alias_cols + remaining_cols
    combined_table = combined_table[ordered_columns]

    # Extract unalerted machines from schedule result
    unalerted_machines = schedule_result.unalerted_machines

    # Compact audit summary for UI display (Person 3) and operations
    audit_summary = {
        "operational_threshold": operational_threshold,
        "technician_slots": int(slots),
        "cost_assumptions": {
            "false_negative_cost": cost_cfg.false_negative_cost,
            "false_positive_cost": cost_cfg.false_positive_cost,
        },
        "total_machines": len(combined_table),
        "selected_count": len(schedule_result.selected_machines),
        "deferred_count": len(schedule_result.deferred_machines),
        "unalerted_count": len(unalerted_machines),
        "capacity_utilized": len(schedule_result.selected_machines),
        "capacity_remaining": max(0, int(slots) - len(schedule_result.selected_machines)),
        "baseline_comparison": threshold_result.baseline_comparison if threshold_result else None,
        "cost_difference": threshold_result.cost_difference if threshold_result else None,
    }

    return PipelineResult(
        combined_table=combined_table,
        selected_machines=schedule_result.selected_machines,
        deferred_machines=schedule_result.deferred_machines,
        operational_threshold=operational_threshold,
        threshold_result=threshold_result,
        schedule_result=schedule_result,
        costs=cost_cfg,
        slots=int(slots),
        unalerted_machines=unalerted_machines,
        audit_summary=audit_summary,
    )


def predict_and_schedule(
    telemetry_df: pd.DataFrame,
    y_val: Iterable[int | float | bool] | np.ndarray | pd.Series | None = None,
    p_val: Iterable[float] | np.ndarray | pd.Series | None = None,
    threshold: float | None = None,
    slots: int = 3,
    costs: CostConfig | Mapping[str, Any] | None = None,
    predict_fn: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
    id_column: str | None = None,
) -> PipelineResult:
    """Main integration pipeline accepting raw telemetry, invoking predict_machines, and scheduling.

    Args:
        telemetry_df: pandas DataFrame containing fleet machine telemetry sensor readings.
        y_val: Validation ground-truth binary labels (0/1) for threshold optimization.
        p_val: Validation predicted probabilities corresponding to y_val.
        threshold: Optional pre-selected threshold. If None, y_val and p_val are used to optimize.
        slots: Non-negative integer number of technician slots available (default: 3).
        costs: Configurable cost assumptions (CostConfig or dict). Defaults to FN=20.0, FP=1.0.
        predict_fn: Optional callable implementing predict_machines(telemetry_df).
            If None, attempts dynamic discovery from repository ML modules.
        id_column: Optional name of machine ID column in telemetry_df.

    Returns:
        PipelineResult with combined DataFrame and shift decision results.
    """
    if isinstance(telemetry_df, Path) or (
        isinstance(telemetry_df, str)
        and (Path(telemetry_df).is_file() or any(telemetry_df.lower().endswith(ext) for ext in (".csv", ".json", ".parquet", ".pq")))
    ):
        from engine.file_utils import load_dataframe_or_path

        telemetry_df = load_dataframe_or_path(telemetry_df)
    elif not isinstance(telemetry_df, pd.DataFrame):
        raise TypeError(f"telemetry_df must be a pandas DataFrame, got {type(telemetry_df).__name__}.")

    if len(telemetry_df) == 0:
        raise ValueError("telemetry_df cannot be empty.")

    fn = resolve_predict_machines(predict_fn)
    predictions_df = fn(telemetry_df)

    return integrate_predictions(
        predictions_df=predictions_df,
        y_val=y_val,
        p_val=p_val,
        threshold=threshold,
        slots=slots,
        costs=costs,
        id_column=id_column,
        telemetry_df=telemetry_df,
    )


# Canonical alias for pipeline entry point
run_pipeline = predict_and_schedule
