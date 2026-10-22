"""Threshold selection for failure prediction and cost minimization.

Evaluates failure prediction thresholds across a fixed, documented grid to find
the threshold minimizing the relative operational cost on validation data.

Tie-Breaking Rule:
    When multiple candidate thresholds yield the identical minimum total cost,
    the highest threshold is selected. Rationale: In maintenance shift planning,
    higher thresholds reduce false alerts and dispatch fatigue for the crew
    without incurring any additional cost penalty.

Input Validation:
    - Input arrays must be non-empty and of matching length.
    - y_true must contain only binary labels (0 or 1).
    - Probabilities must be finite numbers bounded within [0.0, 1.0].
    - Evaluated on validation data (do not evaluate on held-out test data).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from engine.cost_model import CostConfig, calculate_cost, validate_cost_config

# Fixed, documented grid of 101 thresholds from 0.00 to 1.00 inclusive (step 0.01)
DEFAULT_THRESHOLD_GRID: np.ndarray = np.round(np.linspace(0.0, 1.0, 101), 4)


@dataclass(frozen=True)
class ThresholdResult:
    """Structured result returned by choose_threshold.

    Attributes:
        threshold: The optimal alert threshold minimizing validation cost.
        min_cost: The minimum total operational cost achieved.
        cost_curve: Complete evaluation curve across all candidate thresholds (pd.DataFrame).
        confusion_matrix: Dictionary containing TP, TN, FP, and FN counts at the selected threshold.
        baseline_comparison: Dictionary comparing selected threshold against baseline threshold 0.50.
    """

    threshold: float
    min_cost: float
    cost_curve: pd.DataFrame
    confusion_matrix: dict[str, int]
    baseline_comparison: dict[str, Any] = field(default_factory=dict)

    @property
    def optimal_threshold(self) -> float:
        """Alias for threshold (optimal threshold minimizing validation cost)."""
        return self.threshold

    @property
    def optimal_cost(self) -> float:
        """Alias for min_cost (minimum validation cost achieved)."""
        return self.min_cost

    @property
    def minimum_cost(self) -> float:
        """Alias for min_cost."""
        return self.min_cost

    @property
    def baseline_threshold(self) -> float:
        """Standard baseline threshold (0.50)."""
        return float(self.baseline_comparison.get("baseline_threshold", 0.50))

    @property
    def baseline_cost(self) -> float:
        """Operational cost evaluated at baseline threshold 0.50."""
        return float(self.baseline_comparison.get("baseline_cost", 0.0))

    @property
    def cost_difference(self) -> float:
        """Cost difference (savings) achieved by optimal threshold vs baseline 0.50.

        Calculated as: baseline_cost - optimal_cost.
        A positive value indicates the reduction in operational penalty units.
        """
        return float(self.baseline_comparison.get("cost_difference", self.baseline_comparison.get("cost_savings", 0.0)))

    @property
    def cost_savings(self) -> float:
        """Cost reduction achieved by optimal threshold vs baseline 0.50."""
        return float(self.baseline_comparison.get("cost_savings", 0.0))

    @property
    def cost_reduction_pct(self) -> float:
        """Percentage cost reduction achieved vs baseline 0.50."""
        return float(self.baseline_comparison.get("cost_reduction_pct", 0.0))

    @property
    def baseline_confusion_matrix(self) -> dict[str, int]:
        """Confusion matrix (TP, TN, FP, FN) evaluated at baseline threshold 0.50."""
        return dict(self.baseline_comparison.get("baseline_confusion_matrix", {}))

    @property
    def is_optimal_better_or_equal(self) -> bool:
        """Whether optimal threshold achieves total cost less than or equal to baseline."""
        return bool(self.baseline_comparison.get("is_optimal_better_or_equal", True))

    @property
    def explanation(self) -> str:
        """Human-readable explanation of threshold optimization vs baseline."""
        return str(self.baseline_comparison.get("explanation", ""))

    @property
    def chart_data(self) -> pd.DataFrame:
        """Cost curve indexed by threshold, ready for direct plotting in Streamlit with st.line_chart()."""
        return self.cost_curve.set_index("threshold")

    def explain(self) -> str:
        """Returns a comprehensive, human-readable summary of the threshold cost analysis."""
        opt_cm = self.confusion_matrix
        base_cm = self.baseline_confusion_matrix
        return (
            f"Explainable Threshold Cost Analysis:\n"
            f"  - Optimal Operational Threshold: {self.threshold:.2f} (Total Cost: {self.min_cost:.2f})\n"
            f"    Confusion Matrix: TP={opt_cm.get('tp', 0)}, TN={opt_cm.get('tn', 0)}, "
            f"FP={opt_cm.get('fp', 0)}, FN={opt_cm.get('fn', 0)}\n"
            f"  - Baseline Threshold: {self.baseline_threshold:.2f} (Total Cost: {self.baseline_cost:.2f})\n"
            f"    Confusion Matrix: TP={base_cm.get('tp', 0)}, TN={base_cm.get('tn', 0)}, "
            f"FP={base_cm.get('fp', 0)}, FN={base_cm.get('fn', 0)}\n"
            f"  - Cost Difference (Savings): {self.cost_difference:.2f} ({self.cost_reduction_pct:.1f}% reduction vs baseline)\n"
            f"  - Operational Decision Rule: Alert when failure probability >= {self.threshold:.2f}\n"
            f"  - Tie-Breaking Rule: Selected highest threshold among candidates with identical minimum cost."
        )

    def get_business_impact(
        self,
        monetary_value_per_unit: float | None = None,
        currency: str = "USD",
    ) -> Any:
        """Calculates executive business impact and cost savings vs baseline threshold 0.50."""
        from engine.business_impact import calculate_business_impact

        return calculate_business_impact(
            self,
            monetary_value_per_unit=monetary_value_per_unit,
            currency=currency,
        )

    @property
    def business_impact(self) -> Any:
        """BusinessImpactResult comparing optimal threshold against baseline threshold 0.50."""
        return self.get_business_impact()

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary representation."""
        return {
            "threshold": self.threshold,
            "min_cost": self.min_cost,
            "optimal_threshold": self.optimal_threshold,
            "optimal_cost": self.optimal_cost,
            "baseline_threshold": self.baseline_threshold,
            "baseline_cost": self.baseline_cost,
            "cost_difference": self.cost_difference,
            "cost_savings": self.cost_savings,
            "cost_reduction_pct": self.cost_reduction_pct,
            "cost_curve": self.cost_curve,
            "confusion_matrix": self.confusion_matrix,
            "baseline_comparison": self.baseline_comparison,
            "explanation": self.explanation,
        }

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            if hasattr(self, key):
                return getattr(self, key)
            if key in self.baseline_comparison:
                return self.baseline_comparison[key]
            raise KeyError(key)
        fields = (
            self.threshold,
            self.min_cost,
            self.cost_curve,
            self.confusion_matrix,
            self.baseline_comparison,
        )
        return fields[key]

    def __iter__(self):
        # Return 4 items for backward compatibility:
        # threshold, min_cost, cost_curve, confusion = choose_threshold(...)
        return iter((self.threshold, self.min_cost, self.cost_curve, self.confusion_matrix))


def choose_threshold(
    y_true: Iterable[int | float | bool] | np.ndarray | pd.Series,
    probabilities: Iterable[float] | np.ndarray | pd.Series,
    costs: CostConfig | Mapping[str, Any] | None = None,
    threshold_grid: Iterable[float] | np.ndarray | None = None,
) -> ThresholdResult:
    """Evaluates candidate thresholds and selects the one with minimum total operational cost.

    Args:
        y_true: Ground-truth binary failure labels (0 or 1).
        probabilities: Predicted failure probabilities in [0.0, 1.0].
        costs: Configurable cost assumptions (CostConfig or dict). Defaults to FN=20, FP=1.
        threshold_grid: Optional custom grid of candidate thresholds. Must include 0.0 and 1.0.
            Defaults to a fixed 101-point grid from 0.0 to 1.0 with step 0.01.

    Returns:
        ThresholdResult dataclass containing:
            - threshold: Selected optimal threshold (float).
            - min_cost: Minimum total cost achieved (float).
            - cost_curve: pandas DataFrame with columns ['threshold', 'tp', 'tn', 'fp', 'fn',
                          'total_cost', 'fn_cost', 'fp_cost'].
            - confusion_matrix: dict with counts {'tp': int, 'tn': int, 'fp': int, 'fn': int}.

    Raises:
        ValueError: If inputs are empty, lengths mismatch, labels are non-binary,
            or probabilities/thresholds are outside [0.0, 1.0] or non-finite.
        TypeError: If input data types or cost configuration are invalid.
    """
    cost_cfg = validate_cost_config(costs)

    if isinstance(y_true, (str, Path)):
        from engine.file_utils import load_dataframe_or_path

        val_df = load_dataframe_or_path(y_true)
        if probabilities is None:
            y_col = next((c for c in ["y_true", "label", "actual", "failure", "ground_truth"] if c in val_df.columns), val_df.columns[0])
            p_col = next((c for c in ["probabilities", "probability", "failure_probability", "p_val", "score"] if c in val_df.columns), val_df.columns[1])
            y_true = val_df[y_col]
            probabilities = val_df[p_col]
        elif isinstance(probabilities, str) and probabilities in val_df.columns:
            y_col = next((c for c in ["y_true", "label", "actual", "failure", "ground_truth"] if c in val_df.columns), val_df.columns[0])
            p_col = probabilities
            y_true = val_df[y_col]
            probabilities = val_df[p_col]

    if isinstance(probabilities, (str, Path)):
        from engine.file_utils import load_dataframe_or_path

        prob_df = load_dataframe_or_path(probabilities)
        p_col = next((c for c in ["probabilities", "probability", "failure_probability", "p_val", "score"] if c in prob_df.columns), prob_df.columns[0])
        probabilities = prob_df[p_col]

    # Convert probabilities to float array
    try:
        p_arr = np.asarray(probabilities, dtype=float)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Failed to convert probabilities to numerical float array: {exc}") from exc

    # Convert y_true to float array
    try:
        y_arr = np.asarray(y_true, dtype=float)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"y_true must contain numeric binary labels (0 or 1): {exc}") from exc

    if y_arr.ndim != 1 or p_arr.ndim != 1:
        raise ValueError(
            f"Inputs must be 1-dimensional. Got y_true.ndim={y_arr.ndim}, probabilities.ndim={p_arr.ndim}."
        )

    n_samples = len(y_arr)
    if n_samples == 0 or len(p_arr) == 0:
        raise ValueError("Input arrays y_true and probabilities cannot be empty.")

    if n_samples != len(p_arr):
        raise ValueError(
            f"Input length mismatch: len(y_true)={n_samples} vs len(probabilities)={len(p_arr)}."
        )

    if not np.all(np.isfinite(y_arr)):
        raise ValueError("y_true contains non-finite values (NaN or Inf).")

    if not np.all(np.isfinite(p_arr)):
        raise ValueError("probabilities contains non-finite values (NaN or Inf).")

    # Validate binary labels
    unique_labels = np.unique(y_arr)
    if not set(unique_labels).issubset({0.0, 1.0}):
        raise ValueError(
            f"y_true must contain only binary labels {{0, 1}}. Found: {unique_labels.tolist()}."
        )

    # Validate probabilities bounded in [0, 1]
    if np.any((p_arr < 0.0) | (p_arr > 1.0)):
        raise ValueError("probabilities contains values outside the valid range [0.0, 1.0].")

    # Determine and validate candidate threshold grid
    if threshold_grid is None:
        grid = DEFAULT_THRESHOLD_GRID
    else:
        try:
            grid = np.asarray(threshold_grid, dtype=float)
        except (ValueError, TypeError) as exc:
            raise TypeError(f"Failed to convert threshold_grid to float array: {exc}") from exc

        if grid.ndim != 1 or len(grid) == 0:
            raise ValueError("threshold_grid must be a non-empty 1-dimensional array.")

        if not np.all(np.isfinite(grid)):
            raise ValueError("threshold_grid contains non-finite values.")

        if np.any((grid < 0.0) | (grid > 1.0)):
            raise ValueError("threshold_grid contains values outside [0.0, 1.0].")

        # Fixed grid must include 0.0 and 1.0
        has_zero = np.isclose(np.min(grid), 0.0)
        has_one = np.isclose(np.max(grid), 1.0)
        if not (has_zero and has_one):
            raise ValueError("threshold_grid must include boundary values 0.0 and 1.0.")

        grid = np.sort(np.unique(grid))

    y_bool = (y_arr == 1.0)

    records: list[dict[str, Any]] = []
    for t in grid:
        t_val = float(t)
        # Decision rule: Predict failure when probability >= threshold
        pred_pos = (p_arr >= t_val)

        tp = int(np.sum(y_bool & pred_pos))
        fn = int(np.sum(y_bool & (~pred_pos)))
        fp = int(np.sum((~y_bool) & pred_pos))
        tn = int(np.sum((~y_bool) & (~pred_pos)))

        cost_breakdown = calculate_cost(false_negatives=fn, false_positives=fp, costs=cost_cfg)

        records.append({
            "threshold": t_val,
            "tp": tp,
            "tn": tn,
            "fp": fp,
            "fn": fn,
            "total_cost": cost_breakdown.total_cost,
            "fn_cost": cost_breakdown.fn_cost,
            "fp_cost": cost_breakdown.fp_cost,
        })

    cost_curve_df = pd.DataFrame(records)

    # Select candidate with minimum total cost
    costs_arr = cost_curve_df["total_cost"].to_numpy(dtype=float)
    min_cost_val = float(np.min(costs_arr))
    best_candidates = cost_curve_df[np.isclose(costs_arr, min_cost_val, atol=1e-9)]

    # Deterministic tie-breaking: pick highest threshold among candidates
    best_row = best_candidates.sort_values(by="threshold", ascending=False).iloc[0]

    selected_threshold = float(best_row["threshold"])
    selected_min_cost = float(best_row["total_cost"])
    confusion = {
        "tp": int(best_row["tp"]),
        "tn": int(best_row["tn"]),
        "fp": int(best_row["fp"]),
        "fn": int(best_row["fn"]),
    }

    # Baseline comparison against standard 0.50 threshold (always evaluated directly at 0.50)
    baseline_threshold = 0.50
    base_pred_pos = (p_arr >= baseline_threshold)
    base_tp = int(np.sum(y_bool & base_pred_pos))
    base_fn = int(np.sum(y_bool & (~base_pred_pos)))
    base_fp = int(np.sum((~y_bool) & base_pred_pos))
    base_tn = int(np.sum((~y_bool) & (~base_pred_pos)))
    base_breakdown = calculate_cost(false_negatives=base_fn, false_positives=base_fp, costs=cost_cfg)
    base_cost = float(base_breakdown.total_cost)

    cost_savings = float(base_cost - selected_min_cost)
    reduction_pct = float((cost_savings / base_cost * 100.0) if base_cost > 0 else 0.0)

    baseline_comp = {
        "baseline_threshold": baseline_threshold,
        "baseline_cost": base_cost,
        "baseline_confusion_matrix": {
            "tp": base_tp,
            "tn": base_tn,
            "fp": base_fp,
            "fn": base_fn,
        },
        "selected_threshold": selected_threshold,
        "selected_cost": selected_min_cost,
        "optimal_threshold": selected_threshold,
        "optimal_cost": selected_min_cost,
        "cost_difference": cost_savings,
        "cost_savings": cost_savings,
        "cost_reduction_pct": round(reduction_pct, 2),
        "is_optimal_better_or_equal": bool(selected_min_cost <= base_cost + 1e-9),
        "explanation": (
            f"Cost-optimized threshold {selected_threshold:.2f} achieves total cost {selected_min_cost:.2f} "
            f"vs baseline threshold {baseline_threshold:.2f} cost {base_cost:.2f} "
            f"(savings: {cost_savings:.2f}, {reduction_pct:.1f}% reduction)."
        ),
    }

    return ThresholdResult(
        threshold=selected_threshold,
        min_cost=selected_min_cost,
        cost_curve=cost_curve_df,
        confusion_matrix=confusion,
        baseline_comparison=baseline_comp,
    )
