"""Comprehensive test suite for ForgeGuard Person 2 Cost Savings & Business Impact feature.

Verifies all 10 required business-impact scenarios:
1. Positive savings: baseline 100, optimized 70 -> 30 units and 30%.
2. Zero savings: both 50 -> 0 units and 0%.
3. Negative savings: baseline 50, optimized 65 -> -15 units, 30% cost increase, not claimed as benefit.
4. Zero-cost baseline: handled safely without division-by-zero errors.
5. Confusion-count comparison: FP and FN changes reported separately and correctly.
6. Monetary conversion: configurable value per unit & currency, omitted when not configured.
7. Threshold baseline: strictly compares against actual threshold 0.50, not nearest candidate.
8. Result consistency: to_dict() and explain() agree with calculated business impact.
9. Input validation: invalid costs, missing required fields, and malformed threshold results.
10. Regression: end-to-end integration and compatibility with ThresholdResult and PipelineResult.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
import pytest

from engine.business_impact import (
    BusinessImpactResult,
    ConfusionImpact,
    MonetaryConfig,
    calculate_business_impact,
    compute_business_impact,
    evaluate_business_impact,
)
from engine.cost_model import CostConfig
from engine.pipeline import predict_and_schedule
from engine.threshold import choose_threshold


class TestPositiveSavings:
    """Scenario 1: Positive savings verification."""

    def test_scenario_1_positive_savings_100_to_70(self) -> None:
        """Baseline cost 100 and optimized cost 70 yields savings of 30 units and 30%."""
        res = calculate_business_impact(
            baseline_cost=100.0,
            optimized_cost=70.0,
            baseline_threshold=0.50,
            optimal_threshold=0.35,
        )

        assert isinstance(res, BusinessImpactResult)
        assert res.baseline_cost == pytest.approx(100.0)
        assert res.optimized_cost == pytest.approx(70.0)
        assert res.cost_savings == pytest.approx(30.0)
        assert res.percentage_savings == pytest.approx(30.0)
        assert res.cost_increase_pct == pytest.approx(0.0)
        assert res.is_benefit is True
        assert res.baseline_threshold == 0.50
        assert res.optimal_threshold == 0.35

        # Explain output asserts positive reduction
        explained = res.explain()
        assert "30.00 units (30.0% reduction" in explained
        assert "Positive Cost Savings" in explained


class TestZeroSavings:
    """Scenario 2: Zero savings verification."""

    def test_scenario_2_zero_savings_50_to_50(self) -> None:
        """Baseline cost 50 and optimized cost 50 yields zero savings and 0%."""
        res = calculate_business_impact(
            baseline_cost=50.0,
            optimized_cost=50.0,
            baseline_threshold=0.50,
            optimal_threshold=0.50,
        )

        assert res.baseline_cost == pytest.approx(50.0)
        assert res.optimized_cost == pytest.approx(50.0)
        assert res.cost_savings == pytest.approx(0.0)
        assert res.percentage_savings == pytest.approx(0.0)
        assert res.cost_increase_pct == pytest.approx(0.0)
        assert res.is_benefit is True

        explained = res.explain()
        assert "0.00 units (0.0% change" in explained


class TestNegativeSavings:
    """Scenario 3: Negative savings (cost increase) verification."""

    def test_scenario_3_negative_savings_50_to_65(self) -> None:
        """Baseline cost 50 and optimized cost 65 yields savings of -15 units and 30% cost increase, not a claimed benefit."""
        res = calculate_business_impact(
            baseline_cost=50.0,
            optimized_cost=65.0,
            baseline_threshold=0.50,
            optimal_threshold=0.85,
        )

        assert res.baseline_cost == pytest.approx(50.0)
        assert res.optimized_cost == pytest.approx(65.0)
        assert res.cost_savings == pytest.approx(-15.0)
        assert res.percentage_savings == pytest.approx(-30.0)
        assert res.cost_increase_pct == pytest.approx(30.0)
        # Must NOT claim a benefit
        assert res.is_benefit is False

        # Explanation text must clearly report cost increase and disclaim any benefit
        explained = res.explain()
        assert "-15.00 units" in explained
        assert "30.0% cost increase" in explained
        assert "No cost benefit achieved" in explained


class TestZeroCostBaseline:
    """Scenario 4: Zero-cost baseline safety verification."""

    def test_scenario_4_zero_cost_baseline_both_zero(self) -> None:
        """Zero baseline cost and zero optimized cost handles percentage safely without ZeroDivisionError."""
        res = calculate_business_impact(
            baseline_cost=0.0,
            optimized_cost=0.0,
        )

        assert res.baseline_cost == pytest.approx(0.0)
        assert res.optimized_cost == pytest.approx(0.0)
        assert res.cost_savings == pytest.approx(0.0)
        assert res.percentage_savings == pytest.approx(0.0)
        assert res.cost_increase_pct == pytest.approx(0.0)
        assert res.is_benefit is True
        assert not math.isnan(res.percentage_savings)
        assert not math.isinf(res.percentage_savings)

    def test_scenario_4_zero_cost_baseline_positive_optimized(self) -> None:
        """Zero baseline cost with positive optimized cost handles percentage safely."""
        res = calculate_business_impact(
            baseline_cost=0.0,
            optimized_cost=25.0,
        )

        assert res.baseline_cost == pytest.approx(0.0)
        assert res.optimized_cost == pytest.approx(25.0)
        assert res.cost_savings == pytest.approx(-25.0)
        assert res.percentage_savings == pytest.approx(0.0)
        assert res.is_benefit is False
        assert not math.isnan(res.percentage_savings)
        assert not math.isinf(res.percentage_savings)


class TestConfusionCountComparison:
    """Scenario 5: Separate false-positive and false-negative tracking."""

    def test_scenario_5_confusion_count_comparison(self) -> None:
        """Verify false-positive and false-negative changes are reported separately and correctly."""
        baseline_cm = {"tp": 10, "tn": 40, "fp": 8, "fn": 6}
        optimized_cm = {"tp": 14, "tn": 45, "fp": 3, "fn": 2}

        res = calculate_business_impact(
            baseline_cost=128.0,
            optimized_cost=43.0,
            baseline_confusion=baseline_cm,
            optimized_confusion=optimized_cm,
        )

        ci = res.confusion_impact
        assert isinstance(ci, ConfusionImpact)

        # Baseline confusion
        assert ci.baseline_tp == 10
        assert ci.baseline_tn == 40
        assert ci.baseline_fp == 8
        assert ci.baseline_fn == 6

        # Optimized confusion
        assert ci.optimized_tp == 14
        assert ci.optimized_tn == 45
        assert ci.optimized_fp == 3
        assert ci.optimized_fn == 2

        # False Positives (False Alarms): baseline 8 -> opt 3
        # Reduction is positive (5 fewer false alarms), delta is negative (-5)
        assert ci.fp_reduction == 5
        assert ci.delta_fp == -5
        assert res.fp_reduction == 5
        assert res.delta_fp == -5

        # False Negatives (Missed Failures): baseline 6 -> opt 2
        # Reduction is positive (4 fewer missed failures), delta is negative (-4)
        assert ci.fn_reduction == 4
        assert ci.delta_fn == -4
        assert res.fn_reduction == 4
        assert res.delta_fn == -4

        # True Positives & True Negatives
        assert ci.delta_tp == 4
        assert ci.delta_tn == 5

        # In explain()
        explained = res.explain()
        assert "False Alarms (FP)    : Baseline=8 -> Optimized=3 (reduction: +5, delta: -5)" in explained
        assert "Missed Failures (FN) : Baseline=6 -> Optimized=2 (reduction: +4, delta: -4)" in explained


class TestMonetaryConversion:
    """Scenario 6: Monetary conversion and omission behavior."""

    def test_scenario_6_monetary_conversion_configured(self) -> None:
        """Configured monetary value per unit and currency estimates savings correctly."""
        res = calculate_business_impact(
            baseline_cost=100.0,
            optimized_cost=70.0,
            monetary_value_per_unit=150.0,
            currency="USD",
        )

        assert res.cost_savings == pytest.approx(30.0)
        assert res.monetary_savings == pytest.approx(4500.0)
        assert res.monetary_baseline_cost == pytest.approx(15000.0)
        assert res.monetary_optimized_cost == pytest.approx(10500.0)
        assert res.currency == "USD"
        assert res.monetary_config is not None
        assert res.monetary_config.value_per_unit == 150.0

        explained = res.explain()
        assert "Monetary Valuation (USD):" in explained
        assert "4,500.00 USD" in explained
        assert "15,000.00 USD" in explained
        assert "10,500.00 USD" in explained

    def test_scenario_6_monetary_conversion_with_custom_currency(self) -> None:
        """Custom currency string (e.g. EUR, GBP) is preserved in calculations and explanation."""
        cfg = MonetaryConfig(value_per_unit=50.0, currency="EUR")
        res = calculate_business_impact(
            baseline_cost=60.0,
            optimized_cost=40.0,
            monetary_config=cfg,
        )

        assert res.monetary_savings == pytest.approx(1000.0)
        assert res.currency == "EUR"
        assert "1,000.00 EUR" in res.explain()

    def test_scenario_6_monetary_conversion_omitted_when_not_configured(self) -> None:
        """Confirm that monetary estimates are completely omitted when no monetary conversion is configured."""
        res = calculate_business_impact(
            baseline_cost=100.0,
            optimized_cost=70.0,
        )

        assert res.monetary_config is None
        assert res.monetary_savings is None
        assert res.monetary_baseline_cost is None
        assert res.monetary_optimized_cost is None
        assert res.currency is None

        # to_dict contains None for monetary fields
        d = res.to_dict()
        assert d["monetary_savings"] is None
        assert d["monetary_baseline_cost"] is None
        assert d["monetary_optimized_cost"] is None
        assert d["currency"] is None
        assert d["monetary_value_per_unit"] is None

        # Explanation text omits monetary valuation section
        assert "Monetary Valuation" not in res.explain()


class TestThresholdBaseline:
    """Scenario 7: Strict threshold baseline 0.50 evaluation."""

    def test_scenario_7_threshold_baseline_strictly_050_from_threshold_result(self) -> None:
        """Confirm feature compares against actual threshold 0.50 even when grid excludes 0.50."""
        # Custom grid excluding 0.50 completely
        custom_grid = [0.0, 0.25, 0.75, 1.0]
        y_val = [0, 0, 0, 1, 1, 1]
        probs = [0.10, 0.20, 0.60, 0.40, 0.80, 0.90]

        thresh_res = choose_threshold(
            y_true=y_val,
            probabilities=probs,
            threshold_grid=custom_grid,
        )

        # Baseline comparison was calculated directly at 0.50
        assert thresh_res.baseline_comparison["baseline_threshold"] == 0.50

        # Pass ThresholdResult to calculate_business_impact
        impact = calculate_business_impact(thresh_res)

        assert impact.baseline_threshold == 0.50
        assert impact.baseline_cost == pytest.approx(21.0)
        assert impact.confusion_impact.baseline_fp == 1
        assert impact.confusion_impact.baseline_fn == 1

        # Check ThresholdResult.get_business_impact() helper method
        helper_impact = thresh_res.get_business_impact(monetary_value_per_unit=100.0)
        assert helper_impact.baseline_threshold == 0.50
        assert helper_impact.monetary_savings is not None

        # Check ThresholdResult.business_impact property
        prop_impact = thresh_res.business_impact
        assert prop_impact.baseline_threshold == 0.50

    def test_scenario_7_rejects_non_050_baseline_threshold(self) -> None:
        """Explicitly passing a non-0.50 baseline threshold raises ValueError."""
        with pytest.raises(ValueError, match="Baseline threshold must be strictly 0.50"):
            calculate_business_impact(
                baseline_cost=50.0,
                optimized_cost=40.0,
                baseline_threshold=0.45,
            )


class TestResultConsistency:
    """Scenario 8: to_dict() and explain() consistency."""

    def test_scenario_8_result_consistency(self) -> None:
        """Verify to_dict() and explain() agree with calculated business-impact results."""
        res = calculate_business_impact(
            baseline_cost=100.0,
            optimized_cost=70.0,
            baseline_confusion={"tp": 5, "tn": 20, "fp": 4, "fn": 3},
            optimized_confusion={"tp": 7, "tn": 22, "fp": 2, "fn": 1},
            monetary_value_per_unit=50.0,
            currency="USD",
        )

        d = res.to_dict()

        # Dictionary values must match dataclass attributes exactly
        assert d["baseline_cost"] == res.baseline_cost
        assert d["optimized_cost"] == res.optimized_cost
        assert d["cost_savings"] == res.cost_savings
        assert d["percentage_savings"] == res.percentage_savings
        assert d["cost_increase_pct"] == res.cost_increase_pct
        assert d["is_benefit"] == res.is_benefit
        assert d["fp_reduction"] == res.fp_reduction
        assert d["fn_reduction"] == res.fn_reduction
        assert d["delta_fp"] == res.delta_fp
        assert d["delta_fn"] == res.delta_fn
        assert d["monetary_savings"] == res.monetary_savings
        assert d["currency"] == res.currency
        assert d["explanation"] == res.explanation

        # Dictionary item access agrees with attributes
        assert res["cost_savings"] == res.cost_savings
        assert res["percentage_savings"] == res.percentage_savings
        assert res["is_benefit"] == res.is_benefit
        assert res["monetary_savings"] == res.monetary_savings

        # explain() returns the identical explanation string
        assert res.explain() == res.explanation
        assert f"{res.cost_savings:.2f}" in res.explain()
        assert f"{res.percentage_savings:.1f}%" in res.explain()
        assert f"{res.monetary_savings:,.2f}" in res.explain()


class TestInputValidation:
    """Scenario 9: Input validation on costs, configurations, and malformed inputs."""

    def test_scenario_9_invalid_costs(self) -> None:
        """Negative, non-finite, and non-numeric costs are rejected with informative errors."""
        # Negative baseline cost
        with pytest.raises(ValueError, match="baseline_cost must be non-negative"):
            calculate_business_impact(baseline_cost=-10.0, optimized_cost=5.0)

        # Negative optimized cost
        with pytest.raises(ValueError, match="optimized_cost must be non-negative"):
            calculate_business_impact(baseline_cost=50.0, optimized_cost=-5.0)

        # Non-finite costs
        with pytest.raises(ValueError, match="must be finite"):
            calculate_business_impact(baseline_cost=float("inf"), optimized_cost=10.0)

        with pytest.raises(ValueError, match="must be finite"):
            calculate_business_impact(baseline_cost=10.0, optimized_cost=float("nan"))

        # Non-numeric costs
        with pytest.raises(TypeError, match="must be numeric"):
            calculate_business_impact(baseline_cost="one_hundred", optimized_cost=50.0)  # type: ignore

        with pytest.raises(TypeError, match="must be numeric"):
            calculate_business_impact(baseline_cost=True, optimized_cost=50.0)  # type: ignore

    def test_scenario_9_missing_required_costs(self) -> None:
        """Missing baseline or optimized costs raise ValueError."""
        with pytest.raises(ValueError, match="baseline_cost is required"):
            calculate_business_impact(optimized_cost=50.0)

        with pytest.raises(ValueError, match="optimized_cost is required"):
            calculate_business_impact(baseline_cost=50.0)

    def test_scenario_9_malformed_threshold_result(self) -> None:
        """Malformed threshold_result objects or non-mappings raise TypeError."""
        with pytest.raises(TypeError, match="threshold_result must be a ThresholdResult or Mapping"):
            calculate_business_impact(threshold_result=12345)

        with pytest.raises(TypeError, match="threshold_result must be a ThresholdResult or Mapping"):
            calculate_business_impact(threshold_result=["not", "a", "result"])

    def test_scenario_9_invalid_monetary_config(self) -> None:
        """Invalid monetary configuration values raise informative errors."""
        with pytest.raises(ValueError, match="value_per_unit.*must be non-negative"):
            MonetaryConfig(value_per_unit=-50.0)

        with pytest.raises(TypeError, match="value_per_unit.*must be numeric"):
            MonetaryConfig(value_per_unit="fifty")  # type: ignore

        with pytest.raises(ValueError, match="currency must be a non-empty string"):
            MonetaryConfig(value_per_unit=50.0, currency="")

        with pytest.raises(TypeError, match="monetary_config must be an instance of MonetaryConfig"):
            calculate_business_impact(
                baseline_cost=50.0,
                optimized_cost=40.0,
                monetary_config="invalid_type",  # type: ignore
            )

    def test_scenario_9_negative_confusion_counts(self) -> None:
        """Negative confusion counts raise ValueError."""
        with pytest.raises(ValueError, match="cannot be negative"):
            calculate_business_impact(
                baseline_cost=50.0,
                optimized_cost=40.0,
                baseline_confusion={"fp": -2, "fn": 0},
            )


class TestPipelineAndThresholdIntegration:
    """Scenario 10: Regression testing and pipeline integration."""

    def test_scenario_10_threshold_result_integration(self) -> None:
        """ThresholdResult integrates seamlessly with calculate_business_impact and helpers."""
        y_val = [0, 0, 0, 0, 1, 1, 1, 1]
        probs = [0.08, 0.15, 0.22, 0.35, 0.55, 0.72, 0.85, 0.94]

        res = choose_threshold(y_true=y_val, probabilities=probs)

        # compute_business_impact alias
        impact1 = compute_business_impact(res, monetary_value_per_unit=100.0)
        assert impact1.baseline_threshold == 0.50
        assert impact1.cost_savings >= 0.0

        # evaluate_business_impact alias
        impact2 = evaluate_business_impact(res)
        assert impact2.baseline_threshold == 0.50

        # ThresholdResult.business_impact property
        impact3 = res.business_impact
        assert impact3.baseline_threshold == 0.50
        assert impact3.cost_savings == impact1.cost_savings

    def test_scenario_10_pipeline_result_integration(self) -> None:
        """PipelineResult integrates with calculate_business_impact and provides business_impact property."""
        telemetry_df = pd.DataFrame({
            "machine_id": [f"CNC-{i:03d}" for i in range(1, 6)],
            "line": ["Line-A"] * 5,
        })
        y_val = [0, 0, 0, 1, 1]
        p_val = [0.1, 0.2, 0.3, 0.8, 0.9]

        mock_predict = lambda df: pd.DataFrame({
            "machine_id": df["machine_id"],
            "failure_probability": [0.85, 0.75, 0.45, 0.25, 0.10],
            "predicted_failure_mode": ["Bearing Wear"] * 5,
        })

        pipeline_res = predict_and_schedule(
            telemetry_df=telemetry_df,
            y_val=y_val,
            p_val=p_val,
            slots=2,
            predict_fn=mock_predict,
        )

        impact = pipeline_res.get_business_impact(monetary_value_per_unit=500.0, currency="USD")
        assert isinstance(impact, BusinessImpactResult)
        assert impact.baseline_threshold == 0.50
        assert impact.monetary_savings is not None

        # Property access
        assert pipeline_res.business_impact is not None
        assert pipeline_res.business_impact.baseline_threshold == 0.50

    def test_scenario_10_pipeline_without_validation_raises_informative_error(self) -> None:
        """Pipeline execution with fixed threshold raises informative error when requesting business impact."""
        telemetry_df = pd.DataFrame({
            "machine_id": ["CNC-001"],
            "line": ["Line-A"],
        })
        mock_predict = lambda df: pd.DataFrame({
            "machine_id": ["CNC-001"],
            "failure_probability": [0.75],
            "predicted_failure_mode": ["Bearing Wear"],
        })

        pipeline_res = predict_and_schedule(
            telemetry_df=telemetry_df,
            threshold=0.50,  # Fixed threshold, no validation data
            predict_fn=mock_predict,
        )

        assert pipeline_res.business_impact is None
        with pytest.raises(ValueError, match="Cannot calculate business impact without validation"):
            pipeline_res.get_business_impact()
