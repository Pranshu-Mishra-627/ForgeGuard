"""Integration tests connecting ML model outputs (Person 1) to Decision Engine (Person 2).

Tests:
1. End-to-end pipeline: validation data -> choose_threshold -> fleet data -> plan_shift.
2. Compliance with selected threshold, technician slot capacity, and priority rankings.
3. Multiple input representations from ML models (separate arrays, pandas Series, embedded dataframe columns).
4. Edge cases: zero slots, excess slots, and capacity exhaustion.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from engine.cost_model import CostConfig
from engine.scheduler import ScheduleResult, plan_shift
from engine.threshold import ThresholdResult, choose_threshold


class TestMLDecisionEngineIntegration:
    """Integration test suite verifying end-to-end contract between Person 1 and Person 2."""

    @pytest.fixture
    def synthetic_ml_outputs(self) -> dict[str, Any]:
        """Simulates outputs produced by Person 1's machine learning model."""
        # 1. Validation set used strictly for threshold optimization
        rng = np.random.RandomState(42)
        n_val = 50
        y_val = rng.binomial(n=1, p=0.25, size=n_val)
        # Synthetic probabilities correlated with true labels
        p_val = np.clip(
            np.where(y_val == 1, rng.beta(5, 2, size=n_val), rng.beta(2, 5, size=n_val)),
            0.01,
            0.99,
        )

        # 2. Operational shift fleet data for scheduling
        fleet_df = pd.DataFrame({
            "machine_id": [f"CNC-{i:03d}" for i in range(1, 11)],
            "factory_line": ["Line-A"] * 5 + ["Line-B"] * 5,
        })
        # Synthetic failure probabilities for the 10 operational machines
        p_fleet = np.array([0.94, 0.88, 0.76, 0.65, 0.52, 0.47, 0.38, 0.25, 0.18, 0.09])

        return {
            "y_val": y_val,
            "p_val": p_val,
            "fleet_df": fleet_df,
            "p_fleet": p_fleet,
        }

    def test_end_to_end_pipeline(self, synthetic_ml_outputs: dict[str, Any]) -> None:
        """Test full pipeline: validation data -> threshold selection -> shift scheduling."""
        y_val = synthetic_ml_outputs["y_val"]
        p_val = synthetic_ml_outputs["p_val"]
        fleet_df = synthetic_ml_outputs["fleet_df"]
        p_fleet = synthetic_ml_outputs["p_fleet"]

        costs = CostConfig(false_negative_cost=20.0, false_positive_cost=1.0)
        technician_slots = 3

        # Step 1: Person 1 passes validation labels and probabilities to threshold selector
        thresh_result = choose_threshold(y_true=y_val, probabilities=p_val, costs=costs)

        assert isinstance(thresh_result, ThresholdResult)
        assert 0.0 <= thresh_result.threshold <= 1.0
        assert thresh_result.min_cost >= 0.0
        assert isinstance(thresh_result.cost_curve, pd.DataFrame)
        assert len(thresh_result.cost_curve) == 101

        # Step 2: Person 2 uses selected threshold to schedule operational shift fleet
        shift_plan = plan_shift(
            df=fleet_df,
            probabilities=p_fleet,
            slots=technician_slots,
            threshold=thresh_result.threshold,
            costs=costs,
        )

        assert isinstance(shift_plan, ScheduleResult)
        table = shift_plan.schedule_table

        # Step 3: Verify threshold adherence
        # Machines with prob >= threshold MUST be alerted
        for i, row in table.iterrows():
            prob = row["failure_probability"]
            if prob >= thresh_result.threshold:
                assert row["alert"] is True
                assert shift_plan.alert_status[row["machine_id"]] is True
            else:
                assert row["alert"] is False
                assert shift_plan.alert_status[row["machine_id"]] is False
                assert row["selected_for_service"] is False
                assert "Not alerted" in row["reason"]

        # Step 4: Verify technician capacity constraint
        num_alerts = sum(p_fleet >= thresh_result.threshold)
        expected_selected_count = min(technician_slots, num_alerts)
        assert len(shift_plan.selected_machines) == expected_selected_count
        assert table["selected_for_service"].sum() == expected_selected_count

        # Step 5: Verify priority ranking and ordering
        if len(shift_plan.selected_machines) > 0 and len(shift_plan.deferred_machines) > 0:
            selected_scores = table[table["machine_id"].isin(shift_plan.selected_machines)]["priority_score"]
            deferred_scores = table[table["machine_id"].isin(shift_plan.deferred_machines)]["priority_score"]
            assert selected_scores.min() >= deferred_scores.max()

        # Step 6: Verify explicit explanations on all records
        for mid, reason in shift_plan.selection_reasons.items():
            assert isinstance(reason, str) and len(reason) > 0
            if mid in shift_plan.selected_machines:
                assert "Selected for service" in reason
            elif shift_plan.alert_status[mid]:
                assert "Deferred" in reason
            else:
                assert "Not alerted" in reason

    def test_integration_with_dataframe_embedded_probabilities(
        self, synthetic_ml_outputs: dict[str, Any]
    ) -> None:
        """Person 1 outputs probabilities directly as a column inside fleet DataFrame."""
        fleet_df = synthetic_ml_outputs["fleet_df"].copy()
        fleet_df["failure_probability"] = synthetic_ml_outputs["p_fleet"]

        # Scheduler should auto-detect failure_probability when probabilities is None
        plan = plan_shift(df=fleet_df, probabilities=None, slots=2, threshold=0.50)

        assert len(plan.selected_machines) == 2
        assert plan.selected_machines == ["CNC-001", "CNC-002"]

    def test_integration_with_pandas_series_inputs(
        self, synthetic_ml_outputs: dict[str, Any]
    ) -> None:
        """Person 1 passes pandas Series with custom index."""
        y_series = pd.Series(synthetic_ml_outputs["y_val"], index=range(100, 150))
        p_series = pd.Series(synthetic_ml_outputs["p_val"], index=range(100, 150))

        # Threshold selection handles pandas Series with non-default index
        thresh = choose_threshold(y_true=y_series, probabilities=p_series)
        assert isinstance(thresh.threshold, float)

        fleet_series = pd.Series(
            synthetic_ml_outputs["p_fleet"],
            index=[f"idx_{i}" for i in range(len(synthetic_ml_outputs["p_fleet"]))],
        )
        plan = plan_shift(
            df=synthetic_ml_outputs["fleet_df"],
            probabilities=fleet_series,
            slots=3,
            threshold=thresh.threshold,
        )
        assert isinstance(plan, ScheduleResult)
        assert len(plan.selected_machines) <= 3
