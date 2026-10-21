"""Unit tests for cost model and threshold selection (engine/cost_model.py & engine/threshold.py).

Covers:
- Acceptance Criterion 1: Threshold selection returns a threshold and complete cost curve.
- Acceptance Criterion 2: Cost calculation matches a hand-calculated confusion-matrix example.
- Acceptance Criterion 3: Increasing missed-failure cost does not silently change false-alarm cost.
- Robust validation: Rejection of invalid costs, labels, non-finite values, and mismatched inputs.
- Deterministic tie-breaking for threshold selection.
"""

from __future__ import annotations

import math
import numpy as np
import pandas as pd
import pytest

from engine.cost_model import (
    DEFAULT_FALSE_NEGATIVE_COST,
    DEFAULT_FALSE_POSITIVE_COST,
    CostBreakdown,
    CostConfig,
    calculate_cost,
    validate_cost_config,
)
from engine.threshold import (
    DEFAULT_THRESHOLD_GRID,
    ThresholdResult,
    choose_threshold,
)


class TestCostModel:
    """Tests covering cost calculation formula, parameters, and validations."""

    def test_criterion_2_hand_calculated_confusion_matrix_example(self) -> None:
        """Criterion 2: Cost calculation matches a hand-calculated confusion-matrix example.

        Hand Calculation:
            Given:
                FN = 3 (missed failures)
                FP = 4 (false alarms)
                false_negative_cost = 20.0
                false_positive_cost = 1.0
            Formula:
                total_cost = (20.0 * 3) + (1.0 * 4) = 60.0 + 4.0 = 64.0
        """
        breakdown = calculate_cost(
            false_negatives=3,
            false_positives=4,
            costs=CostConfig(false_negative_cost=20.0, false_positive_cost=1.0),
        )

        assert breakdown.false_negatives == 3
        assert breakdown.false_positives == 4
        assert breakdown.fn_cost == pytest.approx(60.0)
        assert breakdown.fp_cost == pytest.approx(4.0)
        assert breakdown.total_cost == pytest.approx(64.0)
        assert breakdown.false_negative_cost == 20.0
        assert breakdown.false_positive_cost == 1.0

        # Also test with custom costs
        # FN = 2, FP = 5, FN_cost = 50.0, FP_cost = 2.5 -> total = 100.0 + 12.5 = 112.5
        custom = calculate_cost(
            false_negatives=2,
            false_positives=5,
            costs={"false_negative_cost": 50.0, "false_positive_cost": 2.5},
        )
        assert custom.total_cost == pytest.approx(112.5)
        assert custom.fn_cost == pytest.approx(100.0)
        assert custom.fp_cost == pytest.approx(12.5)

    def test_criterion_3_increasing_fn_cost_does_not_change_fp_cost(self) -> None:
        """Criterion 3: Increasing missed-failure cost does not silently change false-alarm cost."""
        base_config = CostConfig()
        assert base_config.false_negative_cost == DEFAULT_FALSE_NEGATIVE_COST  # 20.0
        assert base_config.false_positive_cost == DEFAULT_FALSE_POSITIVE_COST  # 1.0

        # Update only false_negative_cost via CostConfig
        updated_config = CostConfig(false_negative_cost=100.0)
        assert updated_config.false_negative_cost == 100.0
        # False alarm cost must remain exactly the default, untouched
        assert updated_config.false_positive_cost == DEFAULT_FALSE_POSITIVE_COST

        # Update only false_negative_cost via dict
        dict_config = validate_cost_config({"false_negative_cost": 75.0})
        assert dict_config.false_negative_cost == 75.0
        assert dict_config.false_positive_cost == DEFAULT_FALSE_POSITIVE_COST

        # Verify evaluation with different FN costs keeps FP cost calculation independent
        bd_low = calculate_cost(false_negatives=2, false_positives=3, costs={"false_negative_cost": 10.0})
        bd_high = calculate_cost(false_negatives=2, false_positives=3, costs={"false_negative_cost": 100.0})

        # FP contribution must be identical (3 * 1.0 = 3.0)
        assert bd_low.fp_cost == pytest.approx(3.0)
        assert bd_high.fp_cost == pytest.approx(3.0)
        assert bd_low.false_positive_cost == bd_high.false_positive_cost == 1.0

        # FN contribution changes as expected
        assert bd_low.fn_cost == pytest.approx(20.0)
        assert bd_high.fn_cost == pytest.approx(200.0)

    def test_cost_config_rejects_invalid_values(self) -> None:
        """Reject negative, non-numeric, boolean, and non-finite cost parameters."""
        with pytest.raises(ValueError, match="must be non-negative"):
            CostConfig(false_negative_cost=-1.0)

        with pytest.raises(ValueError, match="must be non-negative"):
            CostConfig(false_positive_cost=-0.5)

        with pytest.raises(TypeError, match="must be a numeric value"):
            CostConfig(false_negative_cost=True)  # boolean rejected

        with pytest.raises(TypeError, match="must be a numeric value"):
            CostConfig(false_positive_cost="ten")

        with pytest.raises(ValueError, match="must be finite"):
            CostConfig(false_negative_cost=float("nan"))

        with pytest.raises(ValueError, match="must be finite"):
            CostConfig(false_positive_cost=float("inf"))

    def test_validate_cost_config_rejects_unknown_keys(self) -> None:
        """Reject unknown or misspelled configuration dictionary keys."""
        with pytest.raises(ValueError, match="Unknown cost configuration key"):
            validate_cost_config({"unknown_cost": 50.0})

        with pytest.raises(TypeError, match="Invalid cost configuration type"):
            validate_cost_config([20.0, 1.0])  # type: ignore

    def test_calculate_cost_rejects_invalid_counts(self) -> None:
        """Reject negative counts, floats, and booleans for FN and FP counts."""
        with pytest.raises(ValueError, match="cannot be negative"):
            calculate_cost(false_negatives=-1, false_positives=0)

        with pytest.raises(ValueError, match="cannot be negative"):
            calculate_cost(false_negatives=0, false_positives=-2)

        with pytest.raises(TypeError, match="must be an integer"):
            calculate_cost(false_negatives=2.5, false_positives=0)  # type: ignore

        with pytest.raises(TypeError, match="must be an integer"):
            calculate_cost(false_negatives=True, false_positives=0)  # type: ignore

    def test_calculate_cost_accepts_numpy_integers(self) -> None:
        """Support numpy integer types for confusion counts."""
        res = calculate_cost(false_negatives=np.int64(2), false_positives=np.int32(3))
        assert res.false_negatives == 2
        assert res.false_positives == 3
        assert res.total_cost == pytest.approx(43.0)

    def test_cost_breakdown_dictionary_and_item_access(self) -> None:
        """CostBreakdown supports to_dict and dictionary-style access."""
        bd = calculate_cost(false_negatives=1, false_positives=2)
        d = bd.to_dict()
        assert d["total_cost"] == 22.0
        assert bd["total_cost"] == 22.0
        with pytest.raises(KeyError):
            _ = bd["non_existent_key"]


class TestThresholdSelection:
    """Tests covering threshold grid evaluation, cost curve, and selection rules."""

    def test_criterion_1_returns_threshold_and_complete_cost_curve(self) -> None:
        """Criterion 1: Threshold selection returns a threshold and a complete cost curve."""
        # Simple dataset: 10 validation examples
        y_val = [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]
        probs = [0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95]

        result = choose_threshold(y_true=y_val, probabilities=probs)

        # 1. Selected threshold is valid float in [0.0, 1.0]
        assert isinstance(result.threshold, float)
        assert 0.0 <= result.threshold <= 1.0

        # 2. Cost curve is a pandas DataFrame
        assert isinstance(result.cost_curve, pd.DataFrame)

        # 3. Cost curve has all required columns
        expected_cols = ["threshold", "tp", "tn", "fp", "fn", "total_cost", "fn_cost", "fp_cost"]
        assert list(result.cost_curve.columns) == expected_cols

        # 4. Default grid contains 101 thresholds from 0.0 to 1.0
        assert len(result.cost_curve) == 101
        assert np.isclose(result.cost_curve["threshold"].iloc[0], 0.0)
        assert np.isclose(result.cost_curve["threshold"].iloc[-1], 1.0)

        # 5. Minimum total cost matches minimum in cost curve
        assert result.min_cost == pytest.approx(result.cost_curve["total_cost"].min())

        # 6. Confusion matrix counts match the row of the selected threshold
        selected_row = result.cost_curve[result.cost_curve["threshold"] == result.threshold].iloc[0]
        assert result.confusion_matrix["tp"] == int(selected_row["tp"])
        assert result.confusion_matrix["tn"] == int(selected_row["tn"])
        assert result.confusion_matrix["fp"] == int(selected_row["fp"])
        assert result.confusion_matrix["fn"] == int(selected_row["fn"])

        # Unpacking and item access support
        t, min_c, curve, cm = result
        assert t == result.threshold
        assert min_c == result.min_cost
        assert result["threshold"] == result.threshold

    def test_threshold_selection_finds_optimal_operating_point(self) -> None:
        """Optimal threshold separates positive and negative classes when separable."""
        # Well-separated data: failures have prob >= 0.6, non-failures have prob <= 0.4
        y_val = [0, 0, 0, 1, 1, 1]
        probs = [0.1, 0.2, 0.3, 0.7, 0.8, 0.9]

        res = choose_threshold(y_true=y_val, probabilities=probs)

        # A threshold between 0.31 and 0.70 gives 0 FN and 0 FP -> total cost 0.0
        assert res.min_cost == pytest.approx(0.0)
        assert res.confusion_matrix["fn"] == 0
        assert res.confusion_matrix["fp"] == 0
        assert res.confusion_matrix["tp"] == 3
        assert res.confusion_matrix["tn"] == 3
        assert 0.31 <= res.threshold <= 0.70

    def test_threshold_tie_breaking_picks_highest_threshold(self) -> None:
        """Deterministic tie-breaking rule: Pick highest candidate threshold among tied min costs."""
        # When probabilities are 0.2 and 0.8:
        # For any threshold in (0.2, 0.8], the predictions and cost are identical.
        # The tie-breaker must pick the highest candidate in that interval to minimize false alerts.
        y_val = [0, 1]
        probs = [0.2, 0.8]
        grid = [0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 1.0]

        res = choose_threshold(y_true=y_val, probabilities=probs, threshold_grid=grid)

        # Thresholds 0.3, 0.4, 0.5, 0.6, 0.7 all yield 0 FN, 0 FP (total cost 0).
        # Highest threshold among those is 0.7.
        assert res.min_cost == pytest.approx(0.0)
        assert res.threshold == pytest.approx(0.7)

    def test_threshold_validation_rejects_empty_inputs(self) -> None:
        """Reject empty inputs for y_true or probabilities."""
        with pytest.raises(ValueError, match="cannot be empty"):
            choose_threshold(y_true=[], probabilities=[])

        with pytest.raises(ValueError, match="cannot be empty"):
            choose_threshold(y_true=[1], probabilities=[])

    def test_threshold_validation_rejects_length_mismatch(self) -> None:
        """Reject mismatched lengths between y_true and probabilities."""
        with pytest.raises(ValueError, match="length mismatch"):
            choose_threshold(y_true=[0, 1, 1], probabilities=[0.2, 0.8])

    def test_threshold_validation_rejects_non_binary_labels(self) -> None:
        """Reject labels that are not binary 0 or 1."""
        with pytest.raises(ValueError, match="binary labels"):
            choose_threshold(y_true=[0, 1, 2], probabilities=[0.1, 0.5, 0.8])

        with pytest.raises(ValueError, match="binary labels"):
            choose_threshold(y_true=[-1, 0, 1], probabilities=[0.1, 0.5, 0.8])

        with pytest.raises(ValueError):
            choose_threshold(y_true=["no", "yes"], probabilities=[0.2, 0.8])

    def test_threshold_validation_rejects_invalid_probabilities(self) -> None:
        """Reject probabilities containing NaN, Inf, or outside [0.0, 1.0]."""
        with pytest.raises(ValueError, match="non-finite"):
            choose_threshold(y_true=[0, 1], probabilities=[0.2, float("nan")])

        with pytest.raises(ValueError, match="non-finite"):
            choose_threshold(y_true=[0, 1], probabilities=[0.2, float("inf")])

        with pytest.raises(ValueError, match="outside the valid range"):
            choose_threshold(y_true=[0, 1], probabilities=[-0.05, 0.8])

        with pytest.raises(ValueError, match="outside the valid range"):
            choose_threshold(y_true=[0, 1], probabilities=[0.2, 1.05])

    def test_threshold_custom_grid_requires_boundaries(self) -> None:
        """Custom threshold grid must include boundary values 0.0 and 1.0."""
        # Missing 1.0
        with pytest.raises(ValueError, match="must include boundary values 0.0 and 1.0"):
            choose_threshold(y_true=[0, 1], probabilities=[0.2, 0.8], threshold_grid=[0.0, 0.5])

        # Missing 0.0
        with pytest.raises(ValueError, match="must include boundary values 0.0 and 1.0"):
            choose_threshold(y_true=[0, 1], probabilities=[0.2, 0.8], threshold_grid=[0.2, 1.0])

        # Non-finite grid
        with pytest.raises(ValueError, match="non-finite"):
            choose_threshold(y_true=[0, 1], probabilities=[0.2, 0.8], threshold_grid=[0.0, float("nan"), 1.0])

    def test_threshold_single_class_edge_cases(self) -> None:
        """Threshold selection handles edge case when validation data has all 0s or all 1s."""
        # All zeros: minimum cost occurs when threshold is high enough to produce 0 FP
        all_zeros = choose_threshold(y_true=[0, 0, 0], probabilities=[0.1, 0.2, 0.3])
        assert all_zeros.min_cost == pytest.approx(0.0)

        # All ones: minimum cost occurs when threshold is low enough to catch all failures (0 FN)
        all_ones = choose_threshold(y_true=[1, 1, 1], probabilities=[0.7, 0.8, 0.9])
        assert all_ones.min_cost == pytest.approx(0.0)
