"""Integration tests for Person 1 (ML Predictions) and Person 2 (Decision Engine) pipeline.

Verifies:
1. End-to-end integration: telemetry -> predict_machines -> choose_threshold -> plan_shift -> combined table.
2. Threshold consistency: operational threshold selected from validation data strictly drives scheduling,
   independent of Person 1's model-internal maintenance_alert.
3. Machine ID preservation: order, data types, and values preserved throughout pipeline.
4. Capacity limits: service assignments never exceed technician slot count.
5. Deferred alerts: alerted machines beyond capacity are deferred with explicit explanations.
6. Failure-mode preservation: predicted_failure_mode preserved without modification.
7. Configurable costs & slots: custom cost parameters and technician capacities.
8. Edge cases: zero slots, zero alerts, fewer alerts than slots, tied priority scores.
9. Informative error handling for invalid inputs and missing dependencies.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from engine.cost_model import DEFAULT_FALSE_NEGATIVE_COST, DEFAULT_FALSE_POSITIVE_COST, CostConfig
from engine.pipeline import (
    PipelineResult,
    integrate_predictions,
    predict_and_schedule,
    resolve_predict_machines,
    run_pipeline,
)
from engine.threshold import ThresholdResult, choose_threshold


@pytest.fixture
def sample_validation_data() -> tuple[np.ndarray, np.ndarray]:
    """Generates synthetic validation data (labels and predicted probabilities)."""
    rng = np.random.RandomState(42)
    n_val = 60
    y_val = rng.binomial(n=1, p=0.30, size=n_val)
    # Probabilities correlated with ground truth
    p_val = np.clip(
        np.where(y_val == 1, rng.beta(5, 2, size=n_val), rng.beta(2, 5, size=n_val)),
        0.02,
        0.98,
    )
    return y_val, p_val


@pytest.fixture
def sample_telemetry_df() -> pd.DataFrame:
    """Simulates fleet machine telemetry sensor readings."""
    return pd.DataFrame({
        "machine_id": [f"CNC-{i:03d}" for i in range(1, 11)],
        "vibration_rms": [2.4, 4.8, 1.9, 5.2, 3.1, 4.1, 1.2, 3.8, 2.0, 1.5],
        "temperature_c": [65.2, 88.4, 58.1, 92.0, 71.5, 84.3, 52.0, 79.1, 62.4, 55.0],
        "factory_line": ["Line-A"] * 5 + ["Line-B"] * 5,
    })


def make_mock_predict_machines(
    probabilities: list[float] | None = None,
    failure_modes: list[str] | None = None,
    model_threshold: float = 0.50,
):
    """Factory creating a mock implementation of Person 1's predict_machines(telemetry_df)."""
    def mock_predict(df: pd.DataFrame) -> pd.DataFrame:
        n = len(df)
        probs = (
            probabilities
            if probabilities is not None
            else [0.94, 0.88, 0.76, 0.65, 0.52, 0.47, 0.38, 0.25, 0.18, 0.09][:n]
        )
        modes = (
            failure_modes
            if failure_modes is not None
            else [
                "Bearing Wear",
                "Overheating",
                "Tool Wear",
                "Bearing Wear",
                "Electrical Fault",
                "Overheating",
                "None",
                "None",
                "None",
                "None",
            ][:n]
        )
        p_arr = np.array(probs[:n], dtype=float)
        # Person 1's model-internal maintenance alert (e.g. based on default 0.50)
        maintenance_alert = p_arr >= model_threshold

        return pd.DataFrame({
            "machine_id": df["machine_id"].values,
            "failure_probability": p_arr,
            "predicted_failure_mode": modes[:n],
            "maintenance_alert": maintenance_alert,
        })

    return mock_predict


class TestPipelineIntegration:
    """Test suite for pipeline integrating Person 1 predictions with Person 2 engine."""

    def test_end_to_end_pipeline(
        self,
        sample_telemetry_df: pd.DataFrame,
        sample_validation_data: tuple[np.ndarray, np.ndarray],
    ) -> None:
        """Full pipeline execution with validation data, custom slots, and configurable costs."""
        y_val, p_val = sample_validation_data
        costs = CostConfig(false_negative_cost=25.0, false_positive_cost=2.0)
        slots = 3
        mock_predict = make_mock_predict_machines()

        res = predict_and_schedule(
            telemetry_df=sample_telemetry_df,
            y_val=y_val,
            p_val=p_val,
            slots=slots,
            costs=costs,
            predict_fn=mock_predict,
        )

        assert isinstance(res, PipelineResult)
        assert isinstance(res.threshold_result, ThresholdResult)
        assert 0.0 <= res.operational_threshold <= 1.0

        tbl = res.combined_table
        assert isinstance(tbl, pd.DataFrame)
        assert len(tbl) == len(sample_telemetry_df)

        # 1. Verify required columns
        required_cols = [
            "machine_id",
            "failure_probability",
            "predicted_failure_mode",
            "operational_alert",
            "priority_score",
            "service_assignment",
            "decision_reason",
            "maintenance_alert",
            "alert",
            "selected_for_service",
            "reason",
        ]
        for col in required_cols:
            assert col in tbl.columns, f"Missing required column: {col}"

        # 2. Verify telemetry columns preserved
        assert "factory_line" in tbl.columns
        assert "vibration_rms" in tbl.columns

        # 3. Verify priority score calculation: failure_probability * false_negative_cost
        expected_priorities = tbl["failure_probability"] * costs.false_negative_cost
        np.testing.assert_allclose(tbl["priority_score"].values, expected_priorities.values)

        # 4. Verify capacity limit
        assert len(res.selected_machines) <= slots
        assert tbl["service_assignment"].sum() == len(res.selected_machines)

    def test_threshold_consistency_independent_of_model_alert(
        self, sample_telemetry_df: pd.DataFrame
    ) -> None:
        """Operational threshold strictly drives scheduling; Person 1's maintenance_alert is kept for comparison."""
        # Setup: Person 1's model used 0.50 threshold.
        # But operational cost optimization selects 0.70 threshold.
        # Machine with prob 0.65 has maintenance_alert=True, but operational_alert=False.
        custom_probs = [0.95, 0.85, 0.65, 0.55, 0.40, 0.30, 0.20, 0.10, 0.05, 0.01]
        mock_predict = make_mock_predict_machines(
            probabilities=custom_probs,
            model_threshold=0.50,
        )

        res = predict_and_schedule(
            telemetry_df=sample_telemetry_df,
            threshold=0.70,  # operational threshold
            slots=3,
            predict_fn=mock_predict,
        )

        tbl = res.combined_table

        # Machine CNC-003 has prob 0.65:
        # In Person 1's model: alert was True (0.65 >= 0.50)
        # In Person 2's operational decision: alert is False (0.65 < 0.70)
        cnc_003 = tbl[tbl["machine_id"] == "CNC-003"].iloc[0]
        assert bool(cnc_003["maintenance_alert"]) is True
        assert bool(cnc_003["operational_alert"]) is False
        assert bool(cnc_003["service_assignment"]) is False
        assert "below alert threshold" in cnc_003["decision_reason"]

        # Only CNC-001 (0.95) and CNC-002 (0.85) should trigger operational alerts
        assert res.selected_machines == ["CNC-001", "CNC-002"]
        assert len(res.deferred_machines) == 0

    def test_machine_id_preservation(self, sample_telemetry_df: pd.DataFrame) -> None:
        """Machine IDs, their exact order, and count are strictly preserved."""
        # Use an arbitrary order of machine IDs
        custom_ids = ["M-99", "M-02", "M-45", "M-01", "M-77"]
        telemetry_df = pd.DataFrame({
            "machine_id": custom_ids,
            "temp": [50.0, 60.0, 70.0, 80.0, 90.0],
        })
        mock_predict = make_mock_predict_machines(
            probabilities=[0.9, 0.8, 0.7, 0.6, 0.5],
        )

        res = predict_and_schedule(
            telemetry_df=telemetry_df,
            threshold=0.50,
            slots=2,
            predict_fn=mock_predict,
        )

        # Exact order preserved in combined_table
        assert list(res.combined_table["machine_id"]) == custom_ids

    def test_failure_mode_preservation(self, sample_telemetry_df: pd.DataFrame) -> None:
        """Predicted failure mode strings are preserved without mutation."""
        custom_modes = [
            "Overheating",
            "Tool Wear",
            "Bearing Degradation",
            "Spindle Imbalance",
            "Electrical Surge",
            "Gear Failure",
            "Lubrication Loss",
            "Sensor Drift",
            "None",
            "None",
        ]
        mock_predict = make_mock_predict_machines(failure_modes=custom_modes)

        res = predict_and_schedule(
            telemetry_df=sample_telemetry_df,
            threshold=0.40,
            slots=3,
            predict_fn=mock_predict,
        )

        tbl = res.combined_table
        assert list(tbl["predicted_failure_mode"]) == custom_modes

    def test_capacity_limits_and_deferred_alerts(
        self, sample_telemetry_df: pd.DataFrame
    ) -> None:
        """Technician slots strictly cap dispatches; excess alerts are deferred in priority order."""
        # 6 machines trigger alerts (prob >= 0.50), but only 2 technician slots
        probs = [0.95, 0.90, 0.85, 0.80, 0.75, 0.70, 0.30, 0.20, 0.10, 0.05]
        mock_predict = make_mock_predict_machines(probabilities=probs)

        res = predict_and_schedule(
            telemetry_df=sample_telemetry_df,
            threshold=0.50,
            slots=2,
            predict_fn=mock_predict,
        )

        tbl = res.combined_table

        # Exactly 2 selected
        assert len(res.selected_machines) == 2
        assert res.selected_machines == ["CNC-001", "CNC-002"]
        assert tbl["service_assignment"].sum() == 2

        # 4 deferred
        assert len(res.deferred_machines) == 4
        assert res.deferred_machines == ["CNC-003", "CNC-004", "CNC-005", "CNC-006"]

        # Check deferred reasons
        for mid in res.deferred_machines:
            row = tbl[tbl["machine_id"] == mid].iloc[0]
            assert bool(row["operational_alert"]) is True
            assert bool(row["service_assignment"]) is False
            assert "Deferred" in row["decision_reason"]
            assert "capacity was exhausted" in row["decision_reason"]

    def test_edge_case_zero_technician_slots(
        self, sample_telemetry_df: pd.DataFrame
    ) -> None:
        """When slots = 0, no machines are dispatched, all alerts are deferred."""
        mock_predict = make_mock_predict_machines(
            probabilities=[0.9, 0.8, 0.7, 0.3, 0.2, 0.1, 0.1, 0.1, 0.1, 0.1]
        )

        res = predict_and_schedule(
            telemetry_df=sample_telemetry_df,
            threshold=0.50,
            slots=0,
            predict_fn=mock_predict,
        )

        assert len(res.selected_machines) == 0
        assert len(res.deferred_machines) == 3
        assert res.deferred_machines == ["CNC-001", "CNC-002", "CNC-003"]
        assert not res.combined_table["service_assignment"].any()

        for mid in res.deferred_machines:
            reason = res.selection_reasons[mid]
            assert "zero technician slots" in reason

    def test_edge_case_no_alerts(self, sample_telemetry_df: pd.DataFrame) -> None:
        """When no probabilities meet threshold, 0 machines selected, 0 deferred."""
        mock_predict = make_mock_predict_machines(
            probabilities=[0.2] * 10
        )

        res = predict_and_schedule(
            telemetry_df=sample_telemetry_df,
            threshold=0.50,
            slots=3,
            predict_fn=mock_predict,
        )

        assert len(res.selected_machines) == 0
        assert len(res.deferred_machines) == 0
        assert not res.combined_table["operational_alert"].any()
        assert not res.combined_table["service_assignment"].any()
        for reason in res.combined_table["decision_reason"]:
            assert "Not alerted" in reason

    def test_edge_case_fewer_alerts_than_slots(
        self, sample_telemetry_df: pd.DataFrame
    ) -> None:
        """When fewer alerts exist than slots, unused slots remain unassigned."""
        # Only 1 alert, 4 slots available
        probs = [0.95, 0.3, 0.2, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
        mock_predict = make_mock_predict_machines(probabilities=probs)

        res = predict_and_schedule(
            telemetry_df=sample_telemetry_df,
            threshold=0.50,
            slots=4,
            predict_fn=mock_predict,
        )

        assert len(res.selected_machines) == 1
        assert res.selected_machines == ["CNC-001"]
        assert len(res.deferred_machines) == 0
        assert res.combined_table["service_assignment"].sum() == 1

    def test_deterministic_tie_breaking(self) -> None:
        """Tied priority scores resolved deterministically by ascending machine ID."""
        telemetry = pd.DataFrame({"machine_id": ["CNC-09", "CNC-01", "CNC-05"]})
        mock_predict = lambda df: pd.DataFrame({
            "machine_id": df["machine_id"],
            "failure_probability": [0.80, 0.80, 0.80],
            "predicted_failure_mode": ["Bearing"] * 3,
            "maintenance_alert": [True] * 3,
        })

        res = predict_and_schedule(
            telemetry_df=telemetry,
            threshold=0.50,
            slots=2,
            predict_fn=mock_predict,
        )

        # CNC-01, CNC-05 selected; CNC-09 deferred
        assert res.selected_machines == ["CNC-01", "CNC-05"]
        assert res.deferred_machines == ["CNC-09"]

    def test_integrate_predictions_directly(self) -> None:
        """integrate_predictions works directly with existing prediction DataFrame."""
        preds = pd.DataFrame({
            "machine_id": ["M-1", "M-2"],
            "failure_probability": [0.85, 0.30],
            "predicted_failure_mode": ["Overheating", "None"],
            "maintenance_alert": [True, False],
        })

        res = integrate_predictions(
            predictions_df=preds,
            threshold=0.50,
            slots=1,
        )

        assert res.selected_machines == ["M-1"]
        assert res.deferred_machines == []
        assert res.combined_table["service_assignment"].tolist() == [True, False]

    def test_missing_predict_machines_informative_error(
        self, sample_telemetry_df: pd.DataFrame, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Clear error when predict_machines is not provided and not on PYTHONPATH."""
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if "ml" in name or "predict" in name:
                raise ImportError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(ImportError, match="predict_machines.*not found"):
            resolve_predict_machines(predict_fn=None)

    def test_validation_input_errors(
        self, sample_telemetry_df: pd.DataFrame
    ) -> None:
        """Strict input validation checks on telemetry and prediction DataFrames."""
        mock_predict = make_mock_predict_machines()

        # Empty telemetry DataFrame
        with pytest.raises(ValueError, match="cannot be empty"):
            predict_and_schedule(
                telemetry_df=pd.DataFrame(),
                threshold=0.50,
                predict_fn=mock_predict,
            )

        # Missing threshold and missing validation data
        with pytest.raises(ValueError, match="Operational threshold must be determined"):
            predict_and_schedule(
                telemetry_df=sample_telemetry_df,
                threshold=None,
                y_val=None,
                p_val=None,
                predict_fn=mock_predict,
            )

        # Invalid prediction probabilities from model (NaN)
        bad_predict = lambda df: pd.DataFrame({
            "machine_id": df["machine_id"],
            "failure_probability": [np.nan] * len(df),
            "predicted_failure_mode": ["Bearing"] * len(df),
        })
        with pytest.raises(ValueError, match="non-finite"):
            predict_and_schedule(
                telemetry_df=sample_telemetry_df,
                threshold=0.50,
                predict_fn=bad_predict,
            )

        # Missing predicted_failure_mode in prediction DataFrame
        bad_predict_cols = lambda df: pd.DataFrame({
            "machine_id": df["machine_id"],
            "failure_probability": [0.5] * len(df),
        })
        with pytest.raises(ValueError, match="predicted_failure_mode"):
            predict_and_schedule(
                telemetry_df=sample_telemetry_df,
                threshold=0.50,
                predict_fn=bad_predict_cols,
            )

    def test_run_pipeline_alias(
        self, sample_telemetry_df: pd.DataFrame
    ) -> None:
        """run_pipeline is an exact functional alias of predict_and_schedule."""
        mock_predict = make_mock_predict_machines()

        res1 = predict_and_schedule(
            telemetry_df=sample_telemetry_df,
            threshold=0.50,
            slots=3,
            predict_fn=mock_predict,
        )
        res2 = run_pipeline(
            telemetry_df=sample_telemetry_df,
            threshold=0.50,
            slots=3,
            predict_fn=mock_predict,
        )

        assert res1.selected_machines == res2.selected_machines
        assert res1.deferred_machines == res2.deferred_machines
        pd.testing.assert_frame_equal(res1.combined_table, res2.combined_table)


class TestSpecificUserVerifications:
    """Explicit verification of the 6 criteria requested for Person 1 & 2 integration."""

    @pytest.fixture
    def small_telemetry_df(self) -> pd.DataFrame:
        """A small sample telemetry DataFrame representing 5 operational machines."""
        return pd.DataFrame({
            "machine_id": ["CNC-001", "CNC-002", "CNC-003", "CNC-004", "CNC-005"],
            "vibration_rms": [4.8, 3.9, 3.2, 1.8, 1.1],
            "temperature_c": [88.5, 82.1, 74.0, 58.3, 51.2],
            "factory_line": ["Line-A", "Line-A", "Line-B", "Line-B", "Line-B"],
        })

    @pytest.fixture
    def mock_person_1_predict(self):
        """Mock implementation of Person 1's predict_machines(telemetry_df)."""
        def _predict(telemetry_df: pd.DataFrame) -> pd.DataFrame:
            probs = [0.94, 0.82, 0.61, 0.44, 0.15]
            modes = ["Bearing Wear", "Overheating", "Tool Wear", "Electrical Surge", "None"]
            # Person 1's model-internal threshold alert (e.g. fixed at 0.50)
            model_alerts = [p >= 0.50 for p in probs]
            return pd.DataFrame({
                "machine_id": telemetry_df["machine_id"].values,
                "failure_probability": probs,
                "predicted_failure_mode": modes,
                "maintenance_alert": model_alerts,
            })
        return _predict

    def test_verify_1_preserves_machine_id_prob_and_failure_mode(
        self, small_telemetry_df: pd.DataFrame, mock_person_1_predict
    ) -> None:
        """1. Predictions preserve machine_id, failure_probability, and predicted_failure_mode."""
        res = predict_and_schedule(
            telemetry_df=small_telemetry_df,
            threshold=0.50,
            slots=3,
            predict_fn=mock_person_1_predict,
        )
        tbl = res.combined_table

        # Verify machine_id exact values and order
        assert list(tbl["machine_id"]) == ["CNC-001", "CNC-002", "CNC-003", "CNC-004", "CNC-005"]
        # Verify failure_probability exact numerical values
        np.testing.assert_allclose(tbl["failure_probability"].values, [0.94, 0.82, 0.61, 0.44, 0.15])
        # Verify predicted_failure_mode exact strings
        assert list(tbl["predicted_failure_mode"]) == [
            "Bearing Wear",
            "Overheating",
            "Tool Wear",
            "Electrical Surge",
            "None",
        ]

    def test_verify_2_operational_alert_calculated_using_selected_threshold(
        self, small_telemetry_df: pd.DataFrame, mock_person_1_predict
    ) -> None:
        """2. The operational alert is calculated using Person 2’s selected threshold."""
        # Operational threshold = 0.55.
        # CNC-003 has prob 0.61 (>= 0.55 -> True)
        # CNC-004 has prob 0.44 (< 0.55 -> False)
        # CNC-002 has prob 0.82 (>= 0.55 -> True)
        # Person 1's model used 0.50; our operational alert must strictly use 0.55.
        res = predict_and_schedule(
            telemetry_df=small_telemetry_df,
            threshold=0.55,
            slots=3,
            predict_fn=mock_person_1_predict,
        )
        tbl = res.combined_table

        expected_alerts = [prob >= 0.55 for prob in [0.94, 0.82, 0.61, 0.44, 0.15]]
        assert list(tbl["operational_alert"]) == expected_alerts
        assert list(tbl["alert"]) == expected_alerts

        # Specifically check machine with probability below operational threshold
        cnc_004 = tbl[tbl["machine_id"] == "CNC-004"].iloc[0]
        assert bool(cnc_004["operational_alert"]) is False
        assert "below alert threshold" in cnc_004["decision_reason"]

    def test_verify_3_threshold_minimizes_validation_cost_using_configured_costs(
        self, small_telemetry_df: pd.DataFrame, mock_person_1_predict
    ) -> None:
        """3. The threshold minimizes validation cost using the configured FN/FP costs."""
        rng = np.random.RandomState(42)
        n_val = 50
        y_val = rng.binomial(n=1, p=0.30, size=n_val)
        p_val = np.clip(
            np.where(y_val == 1, rng.beta(6, 2, size=n_val), rng.beta(2, 6, size=n_val)),
            0.01,
            0.99,
        )

        custom_costs = CostConfig(false_negative_cost=30.0, false_positive_cost=2.0)

        res = predict_and_schedule(
            telemetry_df=small_telemetry_df,
            y_val=y_val,
            p_val=p_val,
            slots=2,
            costs=custom_costs,
            predict_fn=mock_person_1_predict,
        )

        thresh_res = res.threshold_result
        assert thresh_res is not None

        # Confirm the threshold achieves the global minimum of the evaluated cost curve
        curve = thresh_res.cost_curve
        min_curve_cost = curve["total_cost"].min()
        assert thresh_res.min_cost == pytest.approx(min_curve_cost)

        # Confirm the selected threshold is within the cost curve and corresponds to that min cost
        matching_rows = curve[curve["total_cost"] == min_curve_cost]
        assert res.operational_threshold in matching_rows["threshold"].values

    def test_verify_4_scheduler_capacity_and_correct_prioritization(
        self, small_telemetry_df: pd.DataFrame, mock_person_1_predict
    ) -> None:
        """4. The scheduler selects no more than available technician slots and prioritizes correctly."""
        # 3 machines alert at threshold 0.50: CNC-001 (0.94), CNC-002 (0.82), CNC-003 (0.61)
        # With 2 slots available, exactly 2 highest-priority machines must be selected.
        slots = 2
        costs = CostConfig(false_negative_cost=20.0, false_positive_cost=1.0)

        res = predict_and_schedule(
            telemetry_df=small_telemetry_df,
            threshold=0.50,
            slots=slots,
            costs=costs,
            predict_fn=mock_person_1_predict,
        )

        # Capacity limit strictly respected
        assert len(res.selected_machines) == slots
        assert res.combined_table["service_assignment"].sum() == slots

        # Correct prioritization: 0.94 and 0.82 selected, 0.61 deferred
        assert res.selected_machines == ["CNC-001", "CNC-002"]
        assert res.deferred_machines == ["CNC-003"]

        # Priority scores match failure_probability * FN_cost
        assert res.combined_table.loc[0, "priority_score"] == pytest.approx(0.94 * 20.0)
        assert res.combined_table.loc[1, "priority_score"] == pytest.approx(0.82 * 20.0)
        assert res.combined_table.loc[2, "priority_score"] == pytest.approx(0.61 * 20.0)

    def test_verify_5_deferred_alerts_include_clear_reasons(
        self, small_telemetry_df: pd.DataFrame, mock_person_1_predict
    ) -> None:
        """5. Deferred alerts include clear reasons."""
        res = predict_and_schedule(
            telemetry_df=small_telemetry_df,
            threshold=0.50,
            slots=2,
            predict_fn=mock_person_1_predict,
        )
        tbl = res.combined_table

        # CNC-003 was alerted but deferred due to slot capacity
        cnc_003 = tbl[tbl["machine_id"] == "CNC-003"].iloc[0]
        assert bool(cnc_003["operational_alert"]) is True
        assert bool(cnc_003["service_assignment"]) is False
        assert "Deferred:" in cnc_003["decision_reason"]
        assert "capacity was exhausted" in cnc_003["decision_reason"]
        assert "2 slots assigned to higher-priority alerts" in cnc_003["decision_reason"]

        # Also test 0 slots: all alerted machines deferred with explicit reason
        res_zero = predict_and_schedule(
            telemetry_df=small_telemetry_df,
            threshold=0.50,
            slots=0,
            predict_fn=mock_person_1_predict,
        )
        for mid in res_zero.deferred_machines:
            reason = res_zero.selection_reasons[mid]
            assert "zero technician slots" in reason

    def test_verify_6_graceful_handling_of_empty_inputs_and_invalid_probabilities(
        self, small_telemetry_df: pd.DataFrame, mock_person_1_predict
    ) -> None:
        """6. The integration handles empty inputs and invalid probabilities gracefully."""
        # A) Empty telemetry DataFrame
        with pytest.raises(ValueError, match="telemetry_df cannot be empty"):
            predict_and_schedule(
                telemetry_df=pd.DataFrame(),
                threshold=0.50,
                predict_fn=mock_person_1_predict,
            )

        # B) Non-DataFrame input
        with pytest.raises(TypeError, match="must be a pandas DataFrame"):
            predict_and_schedule(
                telemetry_df="not_a_df",  # type: ignore
                threshold=0.50,
                predict_fn=mock_person_1_predict,
            )

        # C) Invalid probabilities: NaN
        mock_nan = lambda df: pd.DataFrame({
            "machine_id": df["machine_id"],
            "failure_probability": [np.nan, 0.8, 0.6, 0.4, 0.2],
            "predicted_failure_mode": ["Bearing"] * 5,
        })
        with pytest.raises(ValueError, match="non-finite"):
            predict_and_schedule(
                telemetry_df=small_telemetry_df,
                threshold=0.50,
                predict_fn=mock_nan,
            )

        # D) Invalid probabilities: negative (< 0.0)
        mock_neg = lambda df: pd.DataFrame({
            "machine_id": df["machine_id"],
            "failure_probability": [-0.05, 0.8, 0.6, 0.4, 0.2],
            "predicted_failure_mode": ["Bearing"] * 5,
        })
        with pytest.raises(ValueError, match="outside the valid range"):
            predict_and_schedule(
                telemetry_df=small_telemetry_df,
                threshold=0.50,
                predict_fn=mock_neg,
            )

        # E) Invalid probabilities: > 1.0
        mock_over = lambda df: pd.DataFrame({
            "machine_id": df["machine_id"],
            "failure_probability": [1.25, 0.8, 0.6, 0.4, 0.2],
            "predicted_failure_mode": ["Bearing"] * 5,
        })
        with pytest.raises(ValueError, match="outside the valid range"):
            predict_and_schedule(
                telemetry_df=small_telemetry_df,
                threshold=0.50,
                predict_fn=mock_over,
            )

    def test_pipeline_explainable_threshold_cost_analysis(
        self,
        sample_telemetry_df: pd.DataFrame,
        sample_validation_data: tuple[np.ndarray, np.ndarray],
    ) -> None:
        """Verify pipeline exposes explainable threshold analysis and Streamlit-friendly structures."""
        y_val, p_val = sample_validation_data
        mock_predict = make_mock_predict_machines()

        pipeline_res = predict_and_schedule(
            telemetry_df=sample_telemetry_df,
            y_val=y_val,
            p_val=p_val,
            slots=3,
            predict_fn=mock_predict,
        )

        # 1. Optimal threshold and cost properties
        assert pipeline_res.optimal_threshold == pipeline_res.operational_threshold
        assert pipeline_res.optimal_cost is not None
        assert pipeline_res.threshold_result is not None

        # 2. Cost curve DataFrame for Streamlit
        curve = pipeline_res.cost_curve
        assert isinstance(curve, pd.DataFrame)
        assert list(curve.columns) == ["threshold", "tp", "tn", "fp", "fn", "total_cost", "fn_cost", "fp_cost"]

        # 3. Chart data indexed by threshold for direct st.line_chart()
        chart = pipeline_res.chart_data
        assert isinstance(chart, pd.DataFrame)
        assert chart.index.name == "threshold"
        assert "total_cost" in chart.columns

        # 4. Baseline comparison & cost difference
        base = pipeline_res.baseline_comparison
        assert isinstance(base, dict)
        assert base["baseline_threshold"] == 0.50
        assert pipeline_res.cost_difference is not None
        assert pipeline_res.cost_difference == pytest.approx(base["cost_difference"])

        # 5. Human-readable explanation
        assert isinstance(pipeline_res.explanation, str)
        assert len(pipeline_res.explanation) > 0
        explained = pipeline_res.explain()
        assert "Explainable Threshold Cost Analysis" in explained

        # 6. Audit summary fields
        audit = pipeline_res.audit_summary
        assert "baseline_comparison" in audit
        assert "cost_difference" in audit
        assert audit["cost_difference"] == pipeline_res.cost_difference

    def test_threshold_tuned_strictly_on_validation_never_test_data(
        self,
        sample_telemetry_df: pd.DataFrame,
        sample_validation_data: tuple[np.ndarray, np.ndarray],
    ) -> None:
        """Threshold selection depends only on validation data and is invariant to operational test fleet distributions."""
        y_val, p_val = sample_validation_data

        # Predictor 1: low probability fleet
        mock_low = make_mock_predict_machines(probabilities=[0.1, 0.15, 0.2, 0.25, 0.3] * 2)
        res_low = predict_and_schedule(
            telemetry_df=sample_telemetry_df,
            y_val=y_val,
            p_val=p_val,
            predict_fn=mock_low,
        )

        # Predictor 2: high probability fleet
        mock_high = make_mock_predict_machines(probabilities=[0.7, 0.75, 0.8, 0.85, 0.9] * 2)
        res_high = predict_and_schedule(
            telemetry_df=sample_telemetry_df,
            y_val=y_val,
            p_val=p_val,
            predict_fn=mock_high,
        )

        # Operational threshold chosen MUST be identical because y_val and p_val are identical
        assert res_low.operational_threshold == res_high.operational_threshold
        assert res_low.threshold_result.min_cost == res_high.threshold_result.min_cost


