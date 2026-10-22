"""Integration tests connecting ML model outputs (Person 1) to Decision Engine (Person 2).

Tests:
1. End-to-end pipeline: validation data -> choose_threshold -> fleet data -> plan_shift.
2. Compliance with selected threshold, technician slot capacity, and priority rankings.
3. Multiple input representations from ML models (separate arrays, pandas Series, embedded dataframe columns).
4. Edge cases: zero slots, no alerts, fewer alerts than slots, invalid probabilities, and tied priorities.
5. Strict separation between validation data (threshold selection) and operational/test fleet data.
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

        # Confirm minimum cost matches actual minimum in cost curve
        assert thresh_result.min_cost == pytest.approx(thresh_result.cost_curve["total_cost"].min())

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

        # Step 3: Verify machine IDs preserved in exact original order
        assert list(table["machine_id"]) == list(fleet_df["machine_id"])

        # Step 4: Verify priority score formula: probability * false_negative_cost
        expected_priorities = p_fleet * costs.false_negative_cost
        np.testing.assert_allclose(table["priority_score"].values, expected_priorities)

        # Step 5: Verify threshold adherence
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

        # Step 6: Verify technician capacity constraint (never exceed slots)
        num_alerts = sum(p_fleet >= thresh_result.threshold)
        expected_selected_count = min(technician_slots, num_alerts)
        assert len(shift_plan.selected_machines) == expected_selected_count
        assert table["selected_for_service"].sum() == expected_selected_count

        # Step 7: Verify priority ranking and ordering
        if len(shift_plan.selected_machines) > 0 and len(shift_plan.deferred_machines) > 0:
            selected_scores = table[table["machine_id"].isin(shift_plan.selected_machines)]["priority_score"]
            deferred_scores = table[table["machine_id"].isin(shift_plan.deferred_machines)]["priority_score"]
            assert selected_scores.min() >= deferred_scores.max()

        # Step 8: Verify explicit explanations on all records
        for mid, reason in shift_plan.selection_reasons.items():
            assert isinstance(reason, str) and len(reason) > 0
            if mid in shift_plan.selected_machines:
                assert "Selected for service" in reason
            elif shift_plan.alert_status[mid]:
                assert "Deferred" in reason
            else:
                assert "Not alerted" in reason

    def test_edge_case_zero_technician_slots(self, synthetic_ml_outputs: dict[str, Any]) -> None:
        """Edge case: 0 technician slots selects 0 machines and defers all alerts."""
        fleet_df = synthetic_ml_outputs["fleet_df"]
        p_fleet = synthetic_ml_outputs["p_fleet"]
        threshold = 0.50

        plan = plan_shift(df=fleet_df, probabilities=p_fleet, slots=0, threshold=threshold)

        assert len(plan.selected_machines) == 0
        assert plan.selected_machines == []
        assert not plan.schedule_table["selected_for_service"].any()
        # All alerted machines must be deferred
        alerted_mids = [fleet_df["machine_id"].iloc[i] for i in range(len(p_fleet)) if p_fleet[i] >= threshold]
        assert plan.deferred_machines == alerted_mids
        for mid in alerted_mids:
            assert "zero technician slots" in plan.selection_reasons[mid]

    def test_edge_case_no_alerts_triggered(self, synthetic_ml_outputs: dict[str, Any]) -> None:
        """Edge case: All failure probabilities below threshold results in 0 alerts and 0 dispatches."""
        fleet_df = synthetic_ml_outputs["fleet_df"]
        low_probs = np.full(len(fleet_df), 0.20)
        threshold = 0.50

        plan = plan_shift(df=fleet_df, probabilities=low_probs, slots=3, threshold=threshold)

        assert len(plan.selected_machines) == 0
        assert len(plan.deferred_machines) == 0
        assert not plan.schedule_table["alert"].any()
        assert not plan.schedule_table["selected_for_service"].any()
        for reason in plan.selection_reasons.values():
            assert "Not alerted" in reason

    def test_edge_case_fewer_alerts_than_slots(self, synthetic_ml_outputs: dict[str, Any]) -> None:
        """Edge case: When fewer alerts exist than slots, unused slots remain unassigned."""
        fleet_df = synthetic_ml_outputs["fleet_df"]
        # Only 2 machines exceed threshold 0.50
        custom_probs = [0.90, 0.80, 0.40, 0.30, 0.20, 0.15, 0.10, 0.05, 0.02, 0.01]
        slots = 5  # 5 slots available, only 2 alerts exist

        plan = plan_shift(df=fleet_df, probabilities=custom_probs, slots=slots, threshold=0.50)

        # Exactly 2 assigned, 0 deferred, non-alerts are never assigned
        assert len(plan.selected_machines) == 2
        assert len(plan.deferred_machines) == 0
        assert plan.selected_machines == ["CNC-001", "CNC-002"]
        # Check non-alerts
        for mid in fleet_df["machine_id"].iloc[2:]:
            assert plan.alert_status[mid] is False
            assert "Not alerted" in plan.selection_reasons[mid]

    def test_edge_case_tied_priorities_deterministic_tiebreaking(self) -> None:
        """Edge case: Tied priority scores resolved deterministically by ascending machine ID."""
        df_tied = pd.DataFrame({"machine_id": ["CNC-03", "CNC-01", "CNC-02"]})
        tied_probs = [0.80, 0.80, 0.80]
        slots = 2

        plan1 = plan_shift(df=df_tied, probabilities=tied_probs, slots=slots, threshold=0.50)
        plan2 = plan_shift(df=df_tied, probabilities=tied_probs, slots=slots, threshold=0.50)

        # Alphanumeric ascending: CNC-01, CNC-02 selected; CNC-03 deferred
        assert plan1.selected_machines == ["CNC-01", "CNC-02"]
        assert plan1.deferred_machines == ["CNC-03"]
        assert plan1.selected_machines == plan2.selected_machines
        assert plan1.deferred_machines == plan2.deferred_machines

    def test_edge_case_invalid_probabilities_rejected(self, synthetic_ml_outputs: dict[str, Any]) -> None:
        """Edge case: Invalid probabilities (NaN, Inf, out of bounds) strictly rejected."""
        fleet_df = synthetic_ml_outputs["fleet_df"]
        n = len(fleet_df)

        with pytest.raises(ValueError, match="non-finite"):
            plan_shift(df=fleet_df, probabilities=[np.nan] * n, slots=2, threshold=0.50)

        with pytest.raises(ValueError, match="outside the valid range"):
            plan_shift(df=fleet_df, probabilities=[-0.1] * n, slots=2, threshold=0.50)

        with pytest.raises(ValueError, match="outside the valid range"):
            plan_shift(df=fleet_df, probabilities=[1.1] * n, slots=2, threshold=0.50)

    def test_validation_vs_test_data_separation(self, synthetic_ml_outputs: dict[str, Any]) -> None:
        """Audit check: Threshold is selected only on validation set, not on operational/test fleet data."""
        y_val = synthetic_ml_outputs["y_val"]
        p_val = synthetic_ml_outputs["p_val"]

        # 1. Validation split threshold selection
        val_result = choose_threshold(y_true=y_val, probabilities=p_val)
        selected_threshold = val_result.threshold

        # 2. Operational test fleet evaluation uses the FIXED threshold from validation
        fleet_df = synthetic_ml_outputs["fleet_df"]
        p_fleet = synthetic_ml_outputs["p_fleet"]
        plan = plan_shift(df=fleet_df, probabilities=p_fleet, slots=3, threshold=selected_threshold)

        assert isinstance(plan, ScheduleResult)
        assert len(plan.selected_machines) <= 3

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
