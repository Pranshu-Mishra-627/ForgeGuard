"""Cost Savings & Business Impact analysis for ForgeGuard Decision Engine (Person 2).

Translates operational cost minimization and threshold optimization results into
actionable executive metrics, quantified cost savings, confusion-count comparisons,
and optional monetary value projections.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np


@dataclass(frozen=True)
class MonetaryConfig:
    """Configuration for converting relative operational cost units into monetary estimates.

    Attributes:
        value_per_unit: Monetary currency value per single relative cost unit (e.g. 500.0 $/unit).
                        Must be a non-negative finite number.
        currency: Currency symbol or ISO code (e.g., 'USD', '$', 'EUR', 'GBP'). Default is 'USD'.
    """

    value_per_unit: float
    currency: str = "USD"

    def __post_init__(self) -> None:
        if isinstance(self.value_per_unit, bool) or not isinstance(self.value_per_unit, (int, float, np.number)):
            raise TypeError(f"'value_per_unit' must be numeric, got {type(self.value_per_unit).__name__}.")
        if not math.isfinite(self.value_per_unit):
            raise ValueError(f"'value_per_unit' must be finite, got {self.value_per_unit}.")
        if self.value_per_unit < 0:
            raise ValueError(f"'value_per_unit' must be non-negative (>= 0), got {self.value_per_unit}.")
        if not isinstance(self.currency, str) or not self.currency.strip():
            raise ValueError("currency must be a non-empty string.")


@dataclass(frozen=True)
class ConfusionImpact:
    """Details changes in confusion matrix counts between baseline (0.50) and optimal thresholds.

    Attributes:
        baseline_tp: True Positives at baseline threshold 0.50.
        baseline_tn: True Negatives at baseline threshold 0.50.
        baseline_fp: False Positives at baseline threshold 0.50.
        baseline_fn: False Negatives at baseline threshold 0.50.
        optimized_tp: True Positives at optimal threshold.
        optimized_tn: True Negatives at optimal threshold.
        optimized_fp: False Positives at optimal threshold.
        optimized_fn: False Negatives at optimal threshold.
        fp_reduction: Reduction in false alarm dispatches (baseline_fp - optimized_fp).
        fn_reduction: Reduction in missed failure events (baseline_fn - optimized_fn).
        delta_fp: Change in false positives (optimized_fp - baseline_fp).
        delta_fn: Change in false negatives (optimized_fn - baseline_fn).
        delta_tp: Change in true positives (optimized_tp - baseline_tp).
        delta_tn: Change in true negatives (optimized_tn - baseline_tn).
    """

    baseline_tp: int
    baseline_tn: int
    baseline_fp: int
    baseline_fn: int
    optimized_tp: int
    optimized_tn: int
    optimized_fp: int
    optimized_fn: int
    fp_reduction: int
    fn_reduction: int
    delta_fp: int
    delta_fn: int
    delta_tp: int
    delta_tn: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_confusion": {
                "tp": self.baseline_tp,
                "tn": self.baseline_tn,
                "fp": self.baseline_fp,
                "fn": self.baseline_fn,
            },
            "optimized_confusion": {
                "tp": self.optimized_tp,
                "tn": self.optimized_tn,
                "fp": self.optimized_fp,
                "fn": self.optimized_fn,
            },
            "fp_reduction": self.fp_reduction,
            "fn_reduction": self.fn_reduction,
            "delta_fp": self.delta_fp,
            "delta_fn": self.delta_fn,
            "delta_tp": self.delta_tp,
            "delta_tn": self.delta_tn,
        }


@dataclass(frozen=True)
class BusinessImpactResult:
    """Comprehensive business impact and cost savings analysis.

    Attributes:
        baseline_threshold: Baseline decision threshold (strictly 0.50).
        optimal_threshold: Cost-optimized decision threshold.
        baseline_cost: Total operational cost at baseline 0.50.
        optimized_cost: Total operational cost at optimal threshold.
        cost_savings: Difference in operational cost (baseline_cost - optimized_cost).
        percentage_savings: Percentage cost reduction relative to baseline (positive for savings,
                            0.0 for zero baseline or zero savings, negative for cost increase).
        cost_increase_pct: Percentage cost increase relative to baseline if costs increased (> 0),
                           otherwise 0.0.
        is_benefit: Boolean flag; True if cost was reduced or remained equal, False if costs increased.
        confusion_impact: Structured confusion count changes between baseline and optimal.
        monetary_config: Monetary configuration used, or None if omitted.
        monetary_savings: Quantified monetary savings in configured currency, or None if omitted.
        monetary_baseline_cost: Baseline monetary cost, or None if omitted.
        monetary_optimized_cost: Optimized monetary cost, or None if omitted.
        currency: Currency symbol or code, or None if monetary conversion is omitted.
        explanation: Detailed, executive-ready explanation of business impact.
    """

    baseline_threshold: float
    optimal_threshold: float
    baseline_cost: float
    optimized_cost: float
    cost_savings: float
    percentage_savings: float
    cost_increase_pct: float
    is_benefit: bool
    confusion_impact: ConfusionImpact
    monetary_config: MonetaryConfig | None = None
    monetary_savings: float | None = None
    monetary_baseline_cost: float | None = None
    monetary_optimized_cost: float | None = None
    currency: str | None = None
    explanation: str = ""

    @property
    def fp_reduction(self) -> int:
        """Reduction in false alarm dispatches (baseline_fp - optimized_fp)."""
        return self.confusion_impact.fp_reduction

    @property
    def fn_reduction(self) -> int:
        """Reduction in missed failures (baseline_fn - optimized_fn)."""
        return self.confusion_impact.fn_reduction

    @property
    def delta_fp(self) -> int:
        """Delta in false alarms (optimized_fp - baseline_fp)."""
        return self.confusion_impact.delta_fp

    @property
    def delta_fn(self) -> int:
        """Delta in missed failures (optimized_fn - baseline_fn)."""
        return self.confusion_impact.delta_fn

    @property
    def delta_tp(self) -> int:
        """Delta in true positives (optimized_tp - baseline_tp)."""
        return self.confusion_impact.delta_tp

    @property
    def delta_tn(self) -> int:
        """Delta in true negatives (optimized_tn - baseline_tn)."""
        return self.confusion_impact.delta_tn

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary representation."""
        d: dict[str, Any] = {
            "baseline_threshold": self.baseline_threshold,
            "optimal_threshold": self.optimal_threshold,
            "baseline_cost": self.baseline_cost,
            "optimized_cost": self.optimized_cost,
            "cost_savings": self.cost_savings,
            "percentage_savings": self.percentage_savings,
            "cost_increase_pct": self.cost_increase_pct,
            "is_benefit": self.is_benefit,
            "confusion_impact": self.confusion_impact.to_dict(),
            "fp_reduction": self.fp_reduction,
            "fn_reduction": self.fn_reduction,
            "delta_fp": self.delta_fp,
            "delta_fn": self.delta_fn,
            "delta_tp": self.delta_tp,
            "delta_tn": self.delta_tn,
            "explanation": self.explanation,
        }
        if self.monetary_config is not None:
            d["monetary_savings"] = self.monetary_savings
            d["monetary_baseline_cost"] = self.monetary_baseline_cost
            d["monetary_optimized_cost"] = self.monetary_optimized_cost
            d["currency"] = self.currency
            d["monetary_value_per_unit"] = self.monetary_config.value_per_unit
        else:
            d["monetary_savings"] = None
            d["monetary_baseline_cost"] = None
            d["monetary_optimized_cost"] = None
            d["currency"] = None
            d["monetary_value_per_unit"] = None
        return d

    def explain(self) -> str:
        """Returns the human-readable executive explanation."""
        return self.explanation

    def __getitem__(self, key: str) -> Any:
        d = self.to_dict()
        if key in d:
            return d[key]
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def __iter__(self):
        return iter((self.cost_savings, self.percentage_savings, self.is_benefit, self.explanation))


def calculate_business_impact(
    threshold_result: Any = None,
    *,
    baseline_cost: float | None = None,
    optimized_cost: float | None = None,
    baseline_confusion: Mapping[str, int] | None = None,
    optimized_confusion: Mapping[str, int] | None = None,
    baseline_threshold: float = 0.50,
    optimal_threshold: float | None = None,
    monetary_value_per_unit: float | None = None,
    currency: str = "USD",
    monetary_config: MonetaryConfig | None = None,
) -> BusinessImpactResult:
    """Calculates cost savings, percentage improvement, confusion impact, and business valuation.

    Accepts either a ThresholdResult instance (or dict representation) or explicit costs/confusion counts.
    Strictly verifies that baseline comparisons are evaluated against threshold 0.50.

    Args:
        threshold_result: Optional ThresholdResult or mapping containing threshold optimization output.
        baseline_cost: Explicit baseline operational cost at threshold 0.50.
        optimized_cost: Explicit operational cost at optimal threshold.
        baseline_confusion: Confusion counts at baseline {'tp', 'tn', 'fp', 'fn'}.
        optimized_confusion: Confusion counts at optimal threshold {'tp', 'tn', 'fp', 'fn'}.
        baseline_threshold: Baseline threshold (must be strictly 0.50).
        optimal_threshold: Optimal decision threshold.
        monetary_value_per_unit: Optional conversion rate per operational penalty unit.
        currency: Currency symbol or code for monetary conversion (default: 'USD').
        monetary_config: Optional MonetaryConfig instance.

    Returns:
        BusinessImpactResult detailing savings, percentage change, confusion delta, and explanation.

    Raises:
        ValueError: If costs are negative or non-finite, baseline threshold is not 0.50,
            or required input data is missing.
        TypeError: If costs or configuration parameters are invalid types.
    """
    # 1. Extract values from threshold_result if provided
    base_c: float | None = baseline_cost
    opt_c: float | None = optimized_cost
    base_thresh: float = baseline_threshold
    opt_thresh: float | None = optimal_threshold
    b_cm: dict[str, int] = dict(baseline_confusion) if baseline_confusion is not None else {}
    o_cm: dict[str, int] = dict(optimized_confusion) if optimized_confusion is not None else {}

    if threshold_result is not None:
        if hasattr(threshold_result, "threshold") and hasattr(threshold_result, "min_cost"):
            # ThresholdResult dataclass or duck-typed object
            opt_thresh = float(threshold_result.threshold)
            opt_c = float(threshold_result.min_cost)
            if hasattr(threshold_result, "confusion_matrix"):
                o_cm = dict(threshold_result.confusion_matrix)
            if hasattr(threshold_result, "baseline_comparison") and threshold_result.baseline_comparison:
                base_info = threshold_result.baseline_comparison
                base_thresh = float(base_info.get("baseline_threshold", 0.50))
                base_c = float(base_info.get("baseline_cost", 0.0))
                if "baseline_confusion_matrix" in base_info:
                    b_cm = dict(base_info["baseline_confusion_matrix"])
        elif isinstance(threshold_result, Mapping):
            # Mapping / dictionary
            if "min_cost" in threshold_result:
                opt_c = float(threshold_result["min_cost"])
            elif "optimized_cost" in threshold_result:
                opt_c = float(threshold_result["optimized_cost"])
            elif "selected_cost" in threshold_result:
                opt_c = float(threshold_result["selected_cost"])

            if "threshold" in threshold_result:
                opt_thresh = float(threshold_result["threshold"])
            elif "optimal_threshold" in threshold_result:
                opt_thresh = float(threshold_result["optimal_threshold"])

            if "confusion_matrix" in threshold_result:
                o_cm = dict(threshold_result["confusion_matrix"])

            if "baseline_comparison" in threshold_result and isinstance(threshold_result["baseline_comparison"], Mapping):
                base_info = threshold_result["baseline_comparison"]
                base_thresh = float(base_info.get("baseline_threshold", 0.50))
                base_c = float(base_info.get("baseline_cost", 0.0))
                if "baseline_confusion_matrix" in base_info:
                    b_cm = dict(base_info["baseline_confusion_matrix"])
            elif "baseline_cost" in threshold_result:
                base_c = float(threshold_result["baseline_cost"])
                if "baseline_threshold" in threshold_result:
                    base_thresh = float(threshold_result["baseline_threshold"])
                if "baseline_confusion" in threshold_result:
                    b_cm = dict(threshold_result["baseline_confusion"])
                elif "baseline_confusion_matrix" in threshold_result:
                    b_cm = dict(threshold_result["baseline_confusion_matrix"])
        else:
            raise TypeError(
                f"threshold_result must be a ThresholdResult or Mapping, got {type(threshold_result).__name__}."
            )

    # 2. Validate costs
    if base_c is None:
        raise ValueError("baseline_cost is required (or must be present in threshold_result).")
    if opt_c is None:
        raise ValueError("optimized_cost is required (or must be present in threshold_result).")

    if isinstance(base_c, bool) or not isinstance(base_c, (int, float, np.number)):
        raise TypeError(f"baseline_cost must be numeric, got {type(base_c).__name__}.")
    if isinstance(opt_c, bool) or not isinstance(opt_c, (int, float, np.number)):
        raise TypeError(f"optimized_cost must be numeric, got {type(opt_c).__name__}.")

    base_c = float(base_c)
    opt_c = float(opt_c)

    if not math.isfinite(base_c):
        raise ValueError(f"baseline_cost must be finite, got {base_c}.")
    if not math.isfinite(opt_c):
        raise ValueError(f"optimized_cost must be finite, got {opt_c}.")

    if base_c < 0.0:
        raise ValueError(f"baseline_cost must be non-negative (>= 0), got {base_c}.")
    if opt_c < 0.0:
        raise ValueError(f"optimized_cost must be non-negative (>= 0), got {opt_c}.")

    # 3. Validate baseline threshold (strictly 0.50)
    if isinstance(base_thresh, bool) or not isinstance(base_thresh, (int, float, np.number)):
        raise TypeError(f"baseline_threshold must be numeric, got {type(base_thresh).__name__}.")
    base_thresh = float(base_thresh)
    if not math.isclose(base_thresh, 0.50, abs_tol=1e-5):
        raise ValueError(
            f"Baseline threshold must be strictly 0.50 (got {base_thresh}). "
            "ForgeGuard requires benchmarking directly against default operational threshold 0.50."
        )

    if opt_thresh is None:
        opt_thresh = 0.50
    else:
        if isinstance(opt_thresh, bool) or not isinstance(opt_thresh, (int, float, np.number)):
            raise TypeError(f"optimal_threshold must be numeric, got {type(opt_thresh).__name__}.")
        opt_thresh = float(opt_thresh)

    # 4. Monetary configuration resolution
    active_monetary_config: MonetaryConfig | None = None
    if monetary_config is not None:
        if not isinstance(monetary_config, MonetaryConfig):
            raise TypeError(f"monetary_config must be an instance of MonetaryConfig, got {type(monetary_config).__name__}.")
        active_monetary_config = monetary_config
    elif monetary_value_per_unit is not None:
        active_monetary_config = MonetaryConfig(value_per_unit=monetary_value_per_unit, currency=currency)

    # 5. Calculate savings & percentage metrics
    cost_savings = float(base_c - opt_c)

    if base_c > 0.0:
        percentage_savings = float((cost_savings / base_c) * 100.0)
    else:
        # Zero-cost baseline: handle safely without division-by-zero
        percentage_savings = 0.0

    if cost_savings < 0.0:
        # Cost increased; not a benefit
        is_benefit = False
        if base_c > 0.0:
            cost_increase_pct = float(((opt_c - base_c) / base_c) * 100.0)
        else:
            cost_increase_pct = 0.0
    else:
        is_benefit = True
        cost_increase_pct = 0.0

    # 6. Extract and validate confusion counts
    b_tp = int(b_cm.get("tp", 0))
    b_tn = int(b_cm.get("tn", 0))
    b_fp = int(b_cm.get("fp", 0))
    b_fn = int(b_cm.get("fn", 0))

    o_tp = int(o_cm.get("tp", 0))
    o_tn = int(o_cm.get("tn", 0))
    o_fp = int(o_cm.get("fp", 0))
    o_fn = int(o_cm.get("fn", 0))

    for k, v in [
        ("baseline_tp", b_tp),
        ("baseline_tn", b_tn),
        ("baseline_fp", b_fp),
        ("baseline_fn", b_fn),
        ("optimized_tp", o_tp),
        ("optimized_tn", o_tn),
        ("optimized_fp", o_fp),
        ("optimized_fn", o_fn),
    ]:
        if v < 0:
            raise ValueError(f"Confusion count '{k}' cannot be negative, got {v}.")

    confusion_impact = ConfusionImpact(
        baseline_tp=b_tp,
        baseline_tn=b_tn,
        baseline_fp=b_fp,
        baseline_fn=b_fn,
        optimized_tp=o_tp,
        optimized_tn=o_tn,
        optimized_fp=o_fp,
        optimized_fn=o_fn,
        fp_reduction=b_fp - o_fp,
        fn_reduction=b_fn - o_fn,
        delta_fp=o_fp - b_fp,
        delta_fn=o_fn - b_fn,
        delta_tp=o_tp - b_tp,
        delta_tn=o_tn - b_tn,
    )

    # 7. Monetary conversion calculations
    monetary_savings: float | None = None
    monetary_base_cost: float | None = None
    monetary_opt_cost: float | None = None
    curr_str: str | None = None

    if active_monetary_config is not None:
        curr_str = active_monetary_config.currency
        val = active_monetary_config.value_per_unit
        monetary_savings = float(cost_savings * val)
        monetary_base_cost = float(base_c * val)
        monetary_opt_cost = float(opt_c * val)

    # 8. Construct executive-ready explanation
    lines: list[str] = [
        "ForgeGuard Person 2 -- Cost Savings & Business Impact Analysis",
        "=" * 60,
        f"Baseline Threshold : {base_thresh:.2f} | Baseline Operational Cost: {base_c:.2f} units",
        f"Optimal Threshold  : {opt_thresh:.2f} | Optimized Operational Cost: {opt_c:.2f} units",
    ]

    if cost_savings > 0.0:
        lines.append(
            f"Cost Savings: Positive Cost Savings of {cost_savings:.2f} units ({percentage_savings:.1f}% reduction vs baseline threshold 0.50)."
        )
    elif cost_savings == 0.0:
        lines.append(
            "Cost Savings: 0.00 units (0.0% change; optimized cost equals baseline cost)."
        )
    else:
        lines.append(
            f"Cost Savings: {cost_savings:.2f} units ({cost_increase_pct:.1f}% cost increase vs baseline threshold 0.50). "
            "No cost benefit achieved; baseline threshold 0.50 is more cost-effective."
        )

    lines.append("-" * 60)
    lines.append("Confusion Count Impact:")
    lines.append(
        f"  False Alarms (FP)    : Baseline={b_fp} -> Optimized={o_fp} "
        f"(reduction: {confusion_impact.fp_reduction:+d}, delta: {confusion_impact.delta_fp:+d})"
    )
    lines.append(
        f"  Missed Failures (FN) : Baseline={b_fn} -> Optimized={o_fn} "
        f"(reduction: {confusion_impact.fn_reduction:+d}, delta: {confusion_impact.delta_fn:+d})"
    )
    lines.append(
        f"  True Positives (TP)  : Baseline={b_tp} -> Optimized={o_tp} ({confusion_impact.delta_tp:+d}) | "
        f"True Negatives (TN): Baseline={b_tn} -> Optimized={o_tn} ({confusion_impact.delta_tn:+d})"
    )

    if active_monetary_config is not None and monetary_savings is not None:
        lines.append("-" * 60)
        lines.append(f"Monetary Valuation ({curr_str}):")
        lines.append(f"  Conversion Rate      : {active_monetary_config.value_per_unit:.2f} {curr_str} per cost unit")
        if cost_savings >= 0.0:
            lines.append(f"  Monetary Savings     : {monetary_savings:,.2f} {curr_str}")
        else:
            lines.append(f"  Monetary Cost Increase: {-monetary_savings:,.2f} {curr_str}")
        lines.append(f"  Baseline Cost        : {monetary_base_cost:,.2f} {curr_str}")
        lines.append(f"  Optimized Cost       : {monetary_opt_cost:,.2f} {curr_str}")

    explanation_text = "\n".join(lines)

    return BusinessImpactResult(
        baseline_threshold=base_thresh,
        optimal_threshold=opt_thresh,
        baseline_cost=base_c,
        optimized_cost=opt_c,
        cost_savings=cost_savings,
        percentage_savings=percentage_savings,
        cost_increase_pct=cost_increase_pct,
        is_benefit=is_benefit,
        confusion_impact=confusion_impact,
        monetary_config=active_monetary_config,
        monetary_savings=monetary_savings,
        monetary_baseline_cost=monetary_base_cost,
        monetary_optimized_cost=monetary_opt_cost,
        currency=curr_str,
        explanation=explanation_text,
    )


# Aliases for flexible downstream calling
compute_business_impact = calculate_business_impact
evaluate_business_impact = calculate_business_impact
