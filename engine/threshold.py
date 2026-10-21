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

from dataclasses import dataclass
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
    """

    threshold: float
    min_cost: float
    cost_curve: pd.DataFrame
    confusion_matrix: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary representation."""
        return {
            "threshold": self.threshold,
            "min_cost": self.min_cost,
            "cost_curve": self.cost_curve,
            "confusion_matrix": self.confusion_matrix,
        }

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            if hasattr(self, key):
                return getattr(self, key)
            raise KeyError(key)
        fields = (self.threshold, self.min_cost, self.cost_curve, self.confusion_matrix)
        return fields[key]

    def __iter__(self):
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

    return ThresholdResult(
        threshold=selected_threshold,
        min_cost=selected_min_cost,
        cost_curve=cost_curve_df,
        confusion_matrix=confusion,
    )
