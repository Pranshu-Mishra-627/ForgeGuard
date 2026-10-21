"""Unit tests for shift scheduler (engine/scheduler.py).

Covers:
- Acceptance Criterion 4: Zero technician slots selects zero machines.
- Acceptance Criterion 5: More slots than eligible alerts never results in extra assignments.
- Acceptance Criterion 6: Selected machines have priority scores at least as high as deferred alerted machines.
- Acceptance Criterion 7: Tied priorities are resolved deterministically.
- Acceptance Criterion 8: Invalid probabilities, negative slots, and mismatched input lengths are rejected.
- Acceptance Criterion 9: Changing the threshold changes alert eligibility when probabilities cross it.
- Acceptance Criterion 10: Machine IDs are preserved and deferred alerts have explicit explanations.
- Robust validation of identifiers, slot counts, probabilities, thresholds, and result table schema.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.cost_model import CostConfig
from engine.scheduler import ScheduleResult, plan_shift


@pytest.fixture
def sample_machines_df() -> pd.DataFrame:
    """Standard 5-machine sample DataFrame for tests."""
    return pd.DataFrame({
        "machine_id": ["M-001", "M-002", "M-003", "M-004", "M-005"],
        "location": ["Bay-A", "Bay-A", "Bay-B", "Bay-C", "Bay-C"],
    })


class TestShiftScheduler:
    """Comprehensive test suite for plan_shift and ScheduleResult."""

    def test_criterion_4_zero_slots_selects_zero_machines(self, sample_machines_df: pd.DataFrame) -> None:
        """Criterion 4: Zero technician slots selects zero machines."""
        probs = [0.85, 0.75, 0.60, 0.30, 0.10]
        threshold = 0.50  # M-001, M-002, M-003 trigger alerts

        result = plan_shift(
            df=sample_machines_df,
            probabilities=probs,
            slots=0,
            threshold=threshold,
        )

        # 0 machines must be selected
        assert len(result.selected_machines) == 0
        assert result.selected_machines == []

        # All 3 alerted machines must be deferred
        assert len(result.deferred_machines) == 3
        assert result.deferred_machines == ["M-001", "M-002", "M-003"]

        # In result table, selected_for_service is False for all rows
        table = result.schedule_table
        assert not table["selected_for_service"].any()

        # Explanations for alerted machines reflect zero slot capacity
        for mid in result.deferred_machines:
            reason = result.selection_reasons[mid]
            assert "Deferred" in reason
            assert "zero technician slots" in reason

    def test_criterion_5_more_slots_than_alerts_never_results_in_extra_assignments(
        self, sample_machines_df: pd.DataFrame
    ) -> None:
        """Criterion 5: More slots than eligible alerts never results in extra assignments."""
        probs = [0.90, 0.80, 0.20, 0.15, 0.05]
        threshold = 0.50  # Only M-001 and M-002 trigger alerts (2 alerts)
        slots = 10  # 10 slots available, far more than 2 alerts

        result = plan_shift(
            df=sample_machines_df,
            probabilities=probs,
            slots=slots,
            threshold=threshold,
        )

        # Exactly 2 machines selected (only the alerted ones)
        assert len(result.selected_machines) == 2
        assert result.selected_machines == ["M-001", "M-002"]

        # Deferred list is empty because capacity exceeds demand
        assert len(result.deferred_machines) == 0

        # Non-alerted machines must never be selected
        non_alerted = ["M-003", "M-004", "M-005"]
        table = result.schedule_table
        for mid in non_alerted:
            row = table[table["machine_id"] == mid].iloc[0]
            assert row["selected_for_service"] is False or row["selected_for_service"] == False
            assert row["alert"] is False or row["alert"] == False
            assert "Not alerted" in row["reason"]

    def test_criterion_6_selected_priorities_at_least_as_high_as_deferred(
        self, sample_machines_df: pd.DataFrame
    ) -> None:
        """Criterion 6: Selected machines have priority scores at least as high as deferred alerted machines."""
        probs = [0.95, 0.80, 0.70, 0.60, 0.55]
        threshold = 0.50  # All 5 machines alert
        slots = 2  # Only 2 can be selected

        result = plan_shift(
            df=sample_machines_df,
            probabilities=probs,
            slots=slots,
            threshold=threshold,
            costs=CostConfig(false_negative_cost=20.0),
        )

        assert len(result.selected_machines) == 2
        assert len(result.deferred_machines) == 3

        table = result.schedule_table
        selected_scores = table[table["machine_id"].isin(result.selected_machines)]["priority_score"].values
        deferred_scores = table[table["machine_id"].isin(result.deferred_machines)]["priority_score"].values

        # The lowest priority among selected must be >= the highest priority among deferred
        assert min(selected_scores) >= max(deferred_scores)
        assert result.selected_machines == ["M-001", "M-002"]
        assert result.deferred_machines == ["M-003", "M-004", "M-005"]

    def test_criterion_7_tied_priorities_resolved_deterministically(self) -> None:
        """Criterion 7: Tied priorities are resolved deterministically using machine ID ascending order."""
        # M-B and M-A have identical failure probabilities (tied priority scores)
        tied_df = pd.DataFrame({
            "machine_id": ["M-Z", "M-A", "M-B", "M-0"],
        })
        probs = [0.80, 0.80, 0.80, 0.80]
        threshold = 0.50
        slots = 2

        res1 = plan_shift(df=tied_df, probabilities=probs, slots=slots, threshold=threshold)
        res2 = plan_shift(df=tied_df, probabilities=probs, slots=slots, threshold=threshold)

        # Deterministic tie break: Alphanumeric ascending of machine_id -> ['M-0', 'M-A', 'M-B', 'M-Z']
        # Top 2 selected: 'M-0', 'M-A'
        # Remaining 2 deferred: 'M-B', 'M-Z'
        assert res1.selected_machines == ["M-0", "M-A"]
        assert res1.deferred_machines == ["M-B", "M-Z"]

        # Must be strictly reproducible across calls
        assert res1.selected_machines == res2.selected_machines
        assert res1.deferred_machines == res2.deferred_machines

    def test_criterion_8_rejections_of_invalid_inputs(self, sample_machines_df: pd.DataFrame) -> None:
        """Criterion 8: Invalid probabilities, negative slots, and mismatched input lengths are rejected."""
        valid_probs = [0.8, 0.7, 0.6, 0.5, 0.4]

        # 1. Negative slots rejected
        with pytest.raises(ValueError, match="slots must be a non-negative integer"):
            plan_shift(df=sample_machines_df, probabilities=valid_probs, slots=-1, threshold=0.5)

        # 2. Non-integer slots rejected
        with pytest.raises(TypeError, match="slots must be an integer"):
            plan_shift(df=sample_machines_df, probabilities=valid_probs, slots=1.5, threshold=0.5)  # type: ignore

        with pytest.raises(TypeError, match="slots must be an integer"):
            plan_shift(df=sample_machines_df, probabilities=valid_probs, slots=True, threshold=0.5)  # boolean

        # 3. Mismatched input lengths rejected
        with pytest.raises(ValueError, match="Input length mismatch"):
            plan_shift(df=sample_machines_df, probabilities=[0.8, 0.7], slots=2, threshold=0.5)

        # 4. Invalid probabilities: NaN, Inf, out of range [0, 1]
        with pytest.raises(ValueError, match="non-finite"):
            plan_shift(df=sample_machines_df, probabilities=[0.8, 0.7, float("nan"), 0.5, 0.4], slots=2, threshold=0.5)

        with pytest.raises(ValueError, match="non-finite"):
            plan_shift(df=sample_machines_df, probabilities=[0.8, 0.7, float("inf"), 0.5, 0.4], slots=2, threshold=0.5)

        with pytest.raises(ValueError, match="outside the valid range"):
            plan_shift(df=sample_machines_df, probabilities=[0.8, 0.7, -0.01, 0.5, 0.4], slots=2, threshold=0.5)

        with pytest.raises(ValueError, match="outside the valid range"):
            plan_shift(df=sample_machines_df, probabilities=[0.8, 0.7, 1.05, 0.5, 0.4], slots=2, threshold=0.5)

        # 5. Invalid thresholds: <0, >1, NaN, non-numeric
        with pytest.raises(ValueError, match="threshold must be within"):
            plan_shift(df=sample_machines_df, probabilities=valid_probs, slots=2, threshold=-0.1)

        with pytest.raises(ValueError, match="threshold must be within"):
            plan_shift(df=sample_machines_df, probabilities=valid_probs, slots=2, threshold=1.1)

        with pytest.raises(TypeError, match="threshold must be a numeric value"):
            plan_shift(df=sample_machines_df, probabilities=valid_probs, slots=2, threshold="0.5")  # type: ignore

        with pytest.raises(ValueError, match="threshold must be finite"):
            plan_shift(df=sample_machines_df, probabilities=valid_probs, slots=2, threshold=float("nan"))

        # 6. Empty DataFrame rejected
        with pytest.raises(ValueError, match="cannot be empty"):
            plan_shift(df=pd.DataFrame({"machine_id": []}), probabilities=[], slots=2, threshold=0.5)

        # 7. Non-DataFrame rejected
        with pytest.raises(TypeError, match="df must be a pandas DataFrame"):
            plan_shift(df=[{"machine_id": "M-1"}], probabilities=[0.5], slots=1, threshold=0.5)  # type: ignore

    def test_criterion_8_missing_and_duplicate_identifiers_rejected(self) -> None:
        """Reject DataFrames with null, missing, empty, or duplicate machine IDs."""
        # Null identifier
        df_null = pd.DataFrame({"machine_id": ["M-1", None, "M-3"]})
        with pytest.raises(ValueError, match="missing or null values"):
            plan_shift(df=df_null, probabilities=[0.8, 0.6, 0.4], slots=1, threshold=0.5)

        # Empty string identifier
        df_empty = pd.DataFrame({"machine_id": ["M-1", "   ", "M-3"]})
        with pytest.raises(ValueError, match="empty values"):
            plan_shift(df=df_empty, probabilities=[0.8, 0.6, 0.4], slots=1, threshold=0.5)

        # Duplicate identifier
        df_dup = pd.DataFrame({"machine_id": ["M-1", "M-2", "M-1"]})
        with pytest.raises(ValueError, match="Duplicate machine identifiers"):
            plan_shift(df=df_dup, probabilities=[0.8, 0.6, 0.4], slots=1, threshold=0.5)

    def test_criterion_9_changing_threshold_changes_alert_eligibility(
        self, sample_machines_df: pd.DataFrame
    ) -> None:
        """Criterion 9: Changing the threshold changes alert eligibility when probabilities cross it."""
        # Probabilities: 0.90, 0.65, 0.45, 0.30, 0.10
        probs = [0.90, 0.65, 0.45, 0.30, 0.10]

        # Case A: Threshold = 0.40 -> M-001 (0.90), M-002 (0.65), M-003 (0.45) alert
        res_low = plan_shift(df=sample_machines_df, probabilities=probs, slots=5, threshold=0.40)
        assert res_low.alert_status["M-003"] is True
        assert "M-003" in res_low.selected_machines

        # Case B: Threshold = 0.50 -> M-003 (0.45) is now below threshold and not alerted
        res_high = plan_shift(df=sample_machines_df, probabilities=probs, slots=5, threshold=0.50)
        assert res_high.alert_status["M-003"] is False
        assert "M-003" not in res_high.selected_machines
        assert "Not alerted" in res_high.selection_reasons["M-003"]

    def test_criterion_10_machine_ids_preserved_and_deferred_have_explanations(
        self, sample_machines_df: pd.DataFrame
    ) -> None:
        """Criterion 10: Machine IDs are preserved and deferred alerts have explicit explanations."""
        probs = [0.90, 0.70, 0.60, 0.20, 0.10]
        threshold = 0.50  # M-001, M-002, M-003 alert
        slots = 1  # Only 1 slot -> M-001 selected, M-002 & M-003 deferred

        result = plan_shift(
            df=sample_machines_df,
            probabilities=probs,
            slots=slots,
            threshold=threshold,
        )

        table = result.schedule_table

        # 1. All machine IDs preserved in exact input order
        assert list(table["machine_id"]) == list(sample_machines_df["machine_id"])

        # 2. Original probabilities preserved exactly
        np.testing.assert_allclose(table["failure_probability"], probs)

        # 3. Required table columns exist
        expected_columns = [
            "machine_id",
            "failure_probability",
            "alert",
            "priority_score",
            "selected_for_service",
            "reason",
        ]
        assert list(table.columns) == expected_columns

        # 4. Deferred machines have explicit explanations stating why they were deferred
        for mid in result.deferred_machines:
            reason = result.selection_reasons[mid]
            assert "Deferred" in reason
            assert "capacity was exhausted" in reason
            assert f"{slots} slots" in reason

        # 5. Selected machine has explicit explanation
        for mid in result.selected_machines:
            reason = result.selection_reasons[mid]
            assert "Selected for service" in reason

        # 6. Non-alerted machines have explicit explanation
        for mid in ["M-004", "M-005"]:
            reason = result.selection_reasons[mid]
            assert "Not alerted" in reason

    def test_probabilities_passed_as_column_in_dataframe(self) -> None:
        """Probabilities can be passed directly as a column within df."""
        df_with_p = pd.DataFrame({
            "machine_id": ["A", "B", "C"],
            "failure_probability": [0.85, 0.40, 0.15],
        })

        result = plan_shift(df=df_with_p, probabilities=None, slots=1, threshold=0.50)
        assert result.selected_machines == ["A"]
        assert len(result.deferred_machines) == 0

        # Also support passing column name string explicitly
        result2 = plan_shift(
            df=df_with_p,
            probabilities="failure_probability",
            slots=1,
            threshold=0.50,
        )
        assert result2.selected_machines == ["A"]

    def test_schedule_result_unpacking_and_item_access(self, sample_machines_df: pd.DataFrame) -> None:
        """ScheduleResult supports unpacking, dictionary keys, and property aliases."""
        probs = [0.8, 0.6, 0.4, 0.2, 0.1]
        res = plan_shift(df=sample_machines_df, probabilities=probs, slots=1, threshold=0.50)

        # Unpacking
        sel, defr, alerts, reasons, tbl = res
        assert sel == res.selected_machines
        assert defr == res.deferred_machines
        assert tbl.equals(res.schedule_table)

        # Dict key access
        assert res["selected_machines"] == res.selected_machines
        assert res["table"].equals(res.schedule_table)
        assert res.table.equals(res.schedule_table)
        assert res.result_table.equals(res.schedule_table)
