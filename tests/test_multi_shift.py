"""Comprehensive test suite for Multi-Shift Maintenance Planner (engine/multi_shift_scheduler.py).

Tests:
1. Allocation Order: Alerted machines allocated strictly by priority order across shifts.
2. Capacity Constraints: Each shift dispatches at most its configured capacity.
3. Carry-Forward Behavior: Unserviced alerts from earlier shifts carry forward to later shifts.
4. Duplicate Prevention: Machines assigned at most once across all shifts by default.
5. Deterministic Ties: Tied priorities broken deterministically by ascending machine ID.
6. Decoupled Escalation: Escalated critical machines highlighted without exceeding shift capacity.
7. Structured Results & Schemas: Grouped shift results, DataFrame schema, to_dict(), explain().
8. Validation & Edge Cases: Zero shifts, zero capacity, no alerts, excess capacity, duplicate IDs,
   invalid probabilities, invalid ordering policy.
9. Integration: Seamless chaining from ScheduleResult and PipelineResult, preserving ML failure modes.
"""

from __future__ import annotations

import pandas as pd
import pytest

from engine.cost_model import CostConfig
from engine.deferred_risk import RiskTierConfig
from engine.multi_shift_scheduler import (
    MultiShiftPlanResult,
    ShiftAssignmentSummary,
    ShiftConfig,
    plan_multi_shift,
)
from engine.pipeline import predict_and_schedule
from engine.scheduler import plan_shift


@pytest.fixture
def sample_fleet_df() -> pd.DataFrame:
    """Standard 6-machine fleet DataFrame."""
    return pd.DataFrame({
        "machine_id": ["CNC-001", "CNC-002", "CNC-003", "CNC-004", "CNC-005", "CNC-006"],
        "bay": ["A", "A", "B", "B", "C", "C"],
    })


class TestMultiShiftAllocationOrder:
    """Requirement 1: Allocate alerted machines across shifts respecting capacity and priority."""

    def test_multi_shift_priority_allocation(self, sample_fleet_df: pd.DataFrame) -> None:
        """Machines are assigned in descending priority order across Shift 1 and Shift 2."""
        probs = [0.95, 0.85, 0.75, 0.65, 0.30, 0.10]
        # Operational threshold 0.50 -> CNC-001..CNC-004 alert (4 alerts).
        # Shift 1 (capacity=2): gets CNC-001 (prob 0.95) and CNC-002 (prob 0.85).
        # Shift 2 (capacity=1): gets CNC-003 (prob 0.75).
        # CNC-004 (prob 0.65) remains still_deferred.
        shifts = [ShiftConfig("Shift_1", 2), ShiftConfig("Shift_2", 1)]

        result = plan_multi_shift(
            df=sample_fleet_df,
            shifts=shifts,
            probabilities=probs,
            threshold=0.50,
        )

        assert isinstance(result, MultiShiftPlanResult)
        assert result.shift_assignments["Shift_1"] == ["CNC-001", "CNC-002"]
        assert result.shift_assignments["Shift_2"] == ["CNC-003"]
        assert result.assigned_machines == ["CNC-001", "CNC-002", "CNC-003"]
        assert result.still_deferred_machines == ["CNC-004"]
        assert result.unalerted_machines == ["CNC-005", "CNC-006"]

    def test_flexible_shift_input_formats(self, sample_fleet_df: pd.DataFrame) -> None:
        """Accepts tuples, dicts, mapping, or integer lists for shifts."""
        probs = [0.90, 0.80, 0.70, 0.60, 0.20, 0.10]

        # 1. Tuples
        res1 = plan_multi_shift(sample_fleet_df, [("Morning", 1), ("Evening", 2)], probabilities=probs, threshold=0.50)
        assert res1.shift_assignments["Morning"] == ["CNC-001"]
        assert res1.shift_assignments["Evening"] == ["CNC-002", "CNC-003"]

        # 2. Dicts
        res2 = plan_multi_shift(
            sample_fleet_df,
            [{"shift_id": "S1", "capacity": 2}, {"shift_id": "S2", "capacity": 1}],
            probabilities=probs,
            threshold=0.50,
        )
        assert res2.shift_assignments["S1"] == ["CNC-001", "CNC-002"]
        assert res2.shift_assignments["S2"] == ["CNC-003"]

        # 3. Mapping
        res3 = plan_multi_shift(sample_fleet_df, {"Day": 2, "Night": 1}, probabilities=probs, threshold=0.50)
        assert res3.shift_assignments["Day"] == ["CNC-001", "CNC-002"]
        assert res3.shift_assignments["Night"] == ["CNC-003"]

        # 4. List of integer capacities
        res4 = plan_multi_shift(sample_fleet_df, [2, 1], probabilities=probs, threshold=0.50)
        assert res4.shift_assignments["Shift_1"] == ["CNC-001", "CNC-002"]
        assert res4.shift_assignments["Shift_2"] == ["CNC-003"]


class TestCarryForwardAndDuplicatePrevention:
    """Requirement 2: Carry deferred machines forward and prevent duplicate assignments."""

    def test_carry_forward_deferral_history_and_reasons(self, sample_fleet_df: pd.DataFrame) -> None:
        """Carried forward machines record deferral history and transparent explanations."""
        probs = [0.90, 0.80, 0.70, 0.60, 0.20, 0.10]
        shifts = [("Shift_1", 1), ("Shift_2", 1), ("Shift_3", 1)]

        result = plan_multi_shift(df=sample_fleet_df, shifts=shifts, probabilities=probs, threshold=0.50)

        # CNC-001 assigned Shift_1 (no deferral)
        cnc1 = result.assignments_table[result.assignments_table["machine_id"] == "CNC-001"].iloc[0]
        assert cnc1["assigned_shift"] == "Shift_1"
        assert cnc1["deferral_history"] == []
        assert "Assigned to Shift_1" in cnc1["reason"]

        # CNC-002 deferred in Shift_1, assigned in Shift_2
        cnc2 = result.assignments_table[result.assignments_table["machine_id"] == "CNC-002"].iloc[0]
        assert cnc2["assigned_shift"] == "Shift_2"
        assert cnc2["deferral_history"] == ["Shift_1"]
        assert "Deferred in Shift_1 due to technician capacity exhaustion; assigned to Shift_2" in cnc2["reason"]

        # CNC-003 deferred in Shift_1, Shift_2, assigned in Shift_3
        cnc3 = result.assignments_table[result.assignments_table["machine_id"] == "CNC-003"].iloc[0]
        assert cnc3["assigned_shift"] == "Shift_3"
        assert cnc3["deferral_history"] == ["Shift_1", "Shift_2"]
        assert "Deferred in Shift_1, Shift_2 due to technician capacity exhaustion; assigned to Shift_3" in cnc3["reason"]

        # CNC-004 deferred across all shifts, still deferred
        cnc4 = result.assignments_table[result.assignments_table["machine_id"] == "CNC-004"].iloc[0]
        assert cnc4["assigned_shift"] is None
        assert cnc4["still_deferred"] == True
        assert cnc4["deferral_history"] == ["Shift_1", "Shift_2", "Shift_3"]
        assert "Deferred across all shifts (Shift_1, Shift_2, Shift_3)" in cnc4["reason"]
        assert "remaining unserviced" in cnc4["reason"]

    def test_duplicate_prevention_default_invariance(self, sample_fleet_df: pd.DataFrame) -> None:
        """Each machine is dispatched at most once by default across all shifts."""
        probs = [0.95, 0.85, 0.75, 0.65, 0.30, 0.10]
        # Total capacity = 6 across 3 shifts; 4 alerts
        shifts = [("S1", 2), ("S2", 2), ("S3", 2)]

        result = plan_multi_shift(df=sample_fleet_df, shifts=shifts, probabilities=probs, threshold=0.50)

        # 4 alerts total, 6 slots available: all 4 alerts dispatched across S1 and S2
        assert len(result.assigned_machines) == 4
        assert len(set(result.assigned_machines)) == 4
        # S3 receives 0 machines because all alerts are serviced
        assert result.shift_assignments["S3"] == []
        assert result.shift_summaries[2].unused_slots == 2

    def test_reassignment_option_behavior(self, sample_fleet_df: pd.DataFrame) -> None:
        """When allow_reassignment=False, no machine assigned more than once; shifts have disjoint machines."""
        probs = [0.90, 0.80, 0.70, 0.60, 0.20, 0.10]
        # 4 alerts, Shift 1 cap 2, Shift 2 cap 2
        res_default = plan_multi_shift(sample_fleet_df, [("S1", 2), ("S2", 2)], probabilities=probs, threshold=0.50)
        assert res_default.shift_assignments["S1"] == ["CNC-001", "CNC-002"]
        assert res_default.shift_assignments["S2"] == ["CNC-003", "CNC-004"]
        assert set(res_default.shift_assignments["S1"]).isdisjoint(set(res_default.shift_assignments["S2"]))


class TestDeterministicTiesAndPolicies:
    """Requirements 1 & 3: Deterministic tie-breaking and scheduling policies."""

    def test_tied_priorities_broken_by_ascending_machine_id(self) -> None:
        """Tied priorities break deterministically by ascending machine ID across shifts."""
        tied_df = pd.DataFrame({
            "machine_id": ["CNC-009", "CNC-002", "CNC-005", "CNC-001"],
            "bay": ["A", "B", "C", "D"],
        })
        probs = [0.75, 0.75, 0.75, 0.75]  # Identical probabilities
        shifts = [("Shift_1", 2), ("Shift_2", 2)]

        result = plan_multi_shift(df=tied_df, shifts=shifts, probabilities=probs, threshold=0.50)

        # Ascending sort: CNC-001, CNC-002, CNC-005, CNC-009
        assert result.shift_assignments["Shift_1"] == ["CNC-001", "CNC-002"]
        assert result.shift_assignments["Shift_2"] == ["CNC-005", "CNC-009"]

    def test_ordering_policy_failure_probability_vs_priority_score(self) -> None:
        """Supports ordering by priority_score (default) or failure_probability."""
        df = pd.DataFrame({"machine_id": ["M-A", "M-B"]})
        # If both have same cost, order is identical
        probs = [0.80, 0.60]
        res = plan_multi_shift(
            df=df,
            shifts=[("S1", 1), ("S2", 1)],
            probabilities=probs,
            threshold=0.50,
            ordering_policy="failure_probability",
        )
        assert res.shift_assignments["S1"] == ["M-A"]
        assert res.shift_assignments["S2"] == ["M-B"]

    def test_threshold_separate_from_shift_capacity(self, sample_fleet_df: pd.DataFrame) -> None:
        """Adding shifts or changing shift capacities never alters alert threshold or alert status."""
        probs = [0.90, 0.70, 0.55, 0.45, 0.30, 0.10]

        # 1 shift with capacity 1
        res1 = plan_multi_shift(sample_fleet_df, [("S1", 1)], probabilities=probs, threshold=0.50)
        # 3 shifts with capacities 10
        res2 = plan_multi_shift(sample_fleet_df, [("S1", 10), ("S2", 10), ("S3", 10)], probabilities=probs, threshold=0.50)

        assert res1.threshold == 0.50
        assert res2.threshold == 0.50
        # Exactly machines with prob >= 0.50 alert in both
        assert list(res1.assignments_table["alert"]) == [True, True, True, False, False, False]
        assert list(res2.assignments_table["alert"]) == [True, True, True, False, False, False]


class TestDecoupledEscalationAndCapacities:
    """Requirement 3: Escalated machines flagged separately without exceeding shift capacity."""

    def test_critical_escalation_does_not_exceed_shift_capacity(self, sample_fleet_df: pd.DataFrame) -> None:
        """Critical-risk machines are flagged as escalated but cannot bypass shift capacity."""
        probs = [0.95, 0.90, 0.85, 0.40, 0.20, 0.10]
        # CNC-001, CNC-002, CNC-003 all prob >= 0.80 (Critical risk tier)
        # Shift 1 capacity = 1 -> ONLY CNC-001 dispatched; CNC-002 and CNC-003 deferred to Shift 2
        shifts = [("Shift_1", 1), ("Shift_2", 1)]

        result = plan_multi_shift(df=sample_fleet_df, shifts=shifts, probabilities=probs, threshold=0.50)

        # Shift 1 has strictly 1 machine
        assert len(result.shift_assignments["Shift_1"]) == 1
        assert result.shift_assignments["Shift_1"] == ["CNC-001"]

        # CNC-002 is escalated and deferred to Shift 2
        row2 = result.assignments_table[result.assignments_table["machine_id"] == "CNC-002"].iloc[0]
        assert row2["is_escalated"] == True
        assert row2["risk_tier"] == "Critical"
        assert row2["assigned_shift"] == "Shift_2"
        assert "[ESCALATION: Critical Risk]" in row2["reason"]

        # CNC-003 is escalated and remains still_deferred
        row3 = result.assignments_table[result.assignments_table["machine_id"] == "CNC-003"].iloc[0]
        assert row3["is_escalated"] == True
        assert row3["risk_tier"] == "Critical"
        assert row3["still_deferred"] == True
        assert "[ESCALATION: Critical Risk]" in row3["reason"]


class TestStructuredResultsAndCompatibility:
    """Requirement 4: Structured results, DataFrame schema, and single-shift compatibility."""

    def test_structured_results_and_dataframe_schema(self, sample_fleet_df: pd.DataFrame) -> None:
        """Consolidated assignments table contains all expected schema fields."""
        probs = [0.90, 0.75, 0.60, 0.30, 0.20, 0.10]
        shifts = [("S1", 1), ("S2", 1)]

        result = plan_multi_shift(sample_fleet_df, shifts, probabilities=probs, threshold=0.50)

        expected_cols = [
            "machine_id",
            "failure_probability",
            "priority_score",
            "alert",
            "risk_tier",
            "is_escalated",
            "escalation_status",
            "assigned_shift",
            "selected_for_service",
            "still_deferred",
            "overall_alert_rank",
            "shift_rank",
            "deferral_history",
            "reason",
        ]
        for col in expected_cols:
            assert col in result.assignments_table.columns

        # Audit summary metrics
        audit = result.audit_summary
        assert audit["total_fleet_count"] == 6
        assert audit["alerted_count"] == 3
        assert audit["total_shifts"] == 2
        assert audit["total_capacity"] == 2
        assert audit["total_assigned"] == 2
        assert audit["total_still_deferred"] == 1
        assert audit["total_unused_slots"] == 0
        assert audit["overall_capacity_utilization"] == 1.0

        # explain()
        explained = result.explain()
        assert "Multi-Shift Maintenance Dispatch Plan" in explained
        assert "S1" in explained
        assert "S2" in explained

        # Single-shift scheduler compatibility properties
        assert result.selected_machines == ["CNC-001", "CNC-002"]
        assert result.deferred_machines == ["CNC-003"]
        assert result.table is result.assignments_table
        assert result.schedule_table is result.assignments_table

        # Tuple unpacking compatibility
        sel, defd, a_stat, reasons, tbl = result
        assert sel == ["CNC-001", "CNC-002"]
        assert defd == ["CNC-003"]

        # get_shift helper
        s1_summary = result.get_shift("S1")
        assert isinstance(s1_summary, ShiftAssignmentSummary)
        assert s1_summary.assigned_machines == ["CNC-001"]

    def test_get_shift_invalid_id_raises_key_error(self, sample_fleet_df: pd.DataFrame) -> None:
        """Querying an unknown shift ID with get_shift raises KeyError."""
        res = plan_multi_shift(sample_fleet_df, [("S1", 1)], probabilities=[0.9, 0.8, 0.7, 0.6, 0.2, 0.1], threshold=0.50)
        with pytest.raises(KeyError, match="Shift ID 'NonExistent' not found"):
            res.get_shift("NonExistent")


class TestValidationAndEdgeCases:
    """Requirement 5: Validation, edge cases, and robust error handling."""

    def test_edge_case_no_alerts_triggered(self, sample_fleet_df: pd.DataFrame) -> None:
        """When no alerts triggered, all shifts have 0 assignments and 0% utilization."""
        probs = [0.10, 0.20, 0.30, 0.25, 0.15, 0.05]
        shifts = [("S1", 2), ("S2", 2)]

        result = plan_multi_shift(sample_fleet_df, shifts, probabilities=probs, threshold=0.50)

        assert result.total_assigned == 0
        assert result.total_still_deferred == 0
        assert result.shift_assignments["S1"] == []
        assert result.shift_assignments["S2"] == []
        assert result.shift_summaries[0].unused_slots == 2
        assert result.shift_summaries[1].unused_slots == 2
        assert result.overall_capacity_utilization == 0.0

    def test_edge_case_zero_shifts(self, sample_fleet_df: pd.DataFrame) -> None:
        """When shifts list is empty, all alerted machines are still deferred."""
        probs = [0.90, 0.70, 0.30, 0.20, 0.10, 0.05]
        result = plan_multi_shift(sample_fleet_df, shifts=[], probabilities=probs, threshold=0.50)

        assert result.total_capacity == 0
        assert result.total_assigned == 0
        assert result.total_still_deferred == 2
        assert result.still_deferred_machines == ["CNC-001", "CNC-002"]
        assert "zero shifts available" in result.selection_reasons["CNC-001"]

    def test_edge_case_zero_capacity_shifts(self, sample_fleet_df: pd.DataFrame) -> None:
        """Zero-capacity shift dispatches 0 machines and carries all alerts forward."""
        probs = [0.90, 0.80, 0.30, 0.20, 0.10, 0.05]
        shifts = [("S1", 0), ("S2", 2)]

        result = plan_multi_shift(sample_fleet_df, shifts=shifts, probabilities=probs, threshold=0.50)

        assert result.shift_assignments["S1"] == []
        assert result.shift_assignments["S2"] == ["CNC-001", "CNC-002"]
        assert result.shift_summaries[0].utilization_rate == 0.0
        assert result.shift_summaries[1].utilization_rate == 1.0

    def test_edge_case_excess_capacity(self, sample_fleet_df: pd.DataFrame) -> None:
        """When capacity exceeds alerts, all alerts are dispatched and unused slots reported."""
        probs = [0.90, 0.30, 0.20, 0.10, 0.05, 0.01]  # 1 alert (CNC-001)
        shifts = [("S1", 2), ("S2", 3)]

        result = plan_multi_shift(sample_fleet_df, shifts=shifts, probabilities=probs, threshold=0.50)

        assert result.shift_assignments["S1"] == ["CNC-001"]
        assert result.shift_assignments["S2"] == []
        assert result.total_unused_slots == 4  # 1 unused in S1, 3 unused in S2

    def test_validation_rejects_duplicate_shift_ids(self, sample_fleet_df: pd.DataFrame) -> None:
        """Duplicate shift IDs raise ValueError."""
        probs = [0.8, 0.7, 0.6, 0.5, 0.4, 0.3]
        shifts = [("Shift_1", 2), ("Shift_1", 2)]

        with pytest.raises(ValueError, match="Duplicate shift ID"):
            plan_multi_shift(sample_fleet_df, shifts, probabilities=probs, threshold=0.50)

    def test_validation_rejects_duplicate_machine_ids(self) -> None:
        """Duplicate machine IDs in fleet DataFrame raise ValueError."""
        dup_df = pd.DataFrame({"machine_id": ["M-1", "M-1"], "bay": ["A", "B"]})
        with pytest.raises(ValueError, match="Machine identifiers must be unique"):
            plan_multi_shift(dup_df, [("S1", 2)], probabilities=[0.8, 0.7], threshold=0.50)

    def test_validation_rejects_negative_and_invalid_capacities(self, sample_fleet_df: pd.DataFrame) -> None:
        """Negative or non-integer capacities raise ValueError/TypeError."""
        probs = [0.8, 0.7, 0.6, 0.5, 0.4, 0.3]

        with pytest.raises(ValueError, match="non-negative integer"):
            plan_multi_shift(sample_fleet_df, [("S1", -1)], probabilities=probs, threshold=0.50)

        with pytest.raises(TypeError, match="must be an integer"):
            plan_multi_shift(sample_fleet_df, [("S1", 2.5)], probabilities=probs, threshold=0.50)  # type: ignore

        with pytest.raises(TypeError, match="must be an integer"):
            plan_multi_shift(sample_fleet_df, [("S1", True)], probabilities=probs, threshold=0.50)  # type: ignore

    def test_validation_rejects_invalid_ordering_policy(self, sample_fleet_df: pd.DataFrame) -> None:
        """Invalid ordering policy raises ValueError."""
        probs = [0.8, 0.7, 0.6, 0.5, 0.4, 0.3]
        with pytest.raises(ValueError, match="Invalid ordering_policy"):
            plan_multi_shift(sample_fleet_df, [("S1", 2)], probabilities=probs, ordering_policy="random")

    def test_validation_rejects_empty_and_invalid_shift_ids(self) -> None:
        """Empty string or non-string/int shift ID raises ValueError/TypeError."""
        with pytest.raises(ValueError, match="non-empty string or integer"):
            ShiftConfig(shift_id="", capacity=2)

        with pytest.raises(ValueError, match="non-empty string or integer"):
            ShiftConfig(shift_id="   ", capacity=2)

    def test_validation_rejects_invalid_probabilities_and_thresholds(
        self, sample_fleet_df: pd.DataFrame
    ) -> None:
        """Probabilities and thresholds outside [0.0, 1.0] or non-finite are rejected."""
        # Probability > 1.0
        with pytest.raises(ValueError, match="outside valid range"):
            plan_multi_shift(sample_fleet_df, [("S1", 2)], probabilities=[1.5, 0.5, 0.4, 0.3, 0.2, 0.1], threshold=0.50)

        # Probability < 0.0
        with pytest.raises(ValueError, match="outside valid range"):
            plan_multi_shift(sample_fleet_df, [("S1", 2)], probabilities=[-0.1, 0.5, 0.4, 0.3, 0.2, 0.1], threshold=0.50)

        # Probability NaN
        with pytest.raises(ValueError, match="non-finite values"):
            plan_multi_shift(sample_fleet_df, [("S1", 2)], probabilities=[float("nan"), 0.5, 0.4, 0.3, 0.2, 0.1], threshold=0.50)

        # Threshold outside [0, 1]
        probs = [0.8, 0.7, 0.6, 0.5, 0.4, 0.3]
        with pytest.raises(ValueError, match="within"):
            plan_multi_shift(sample_fleet_df, [("S1", 2)], probabilities=probs, threshold=1.20)

        # Non-numeric threshold
        with pytest.raises(TypeError, match="must be numeric"):
            plan_multi_shift(sample_fleet_df, [("S1", 2)], probabilities=probs, threshold="invalid")  # type: ignore

    def test_validation_rejects_empty_dataframe(self) -> None:
        """Empty fleet DataFrame raises ValueError."""
        empty_df = pd.DataFrame(columns=["machine_id", "bay"])
        with pytest.raises(ValueError, match="Input DataFrame is empty"):
            plan_multi_shift(empty_df, [("S1", 2)], probabilities=[], threshold=0.50)

    def test_capacity_strictly_respected_under_heavy_backlog(self, sample_fleet_df: pd.DataFrame) -> None:
        """Even with 6 alerted machines, shift dispatches never exceed configured capacities."""
        probs = [0.99, 0.95, 0.90, 0.85, 0.80, 0.75]  # All 6 machines alert
        # Shifts: S1=1 slot, S2=2 slots (Total capacity=3)
        shifts = [("S1", 1), ("S2", 2)]

        result = plan_multi_shift(sample_fleet_df, shifts, probabilities=probs, threshold=0.50)

        assert len(result.shift_assignments["S1"]) == 1
        assert len(result.shift_assignments["S2"]) == 2
        assert result.shift_summaries[0].assigned_count == 1
        assert result.shift_summaries[0].capacity == 1
        assert result.shift_summaries[1].assigned_count == 2
        assert result.shift_summaries[1].capacity == 2
        # Exactly 3 machines assigned, 3 machines still deferred
        assert len(result.assigned_machines) == 3
        assert len(result.still_deferred_machines) == 3
        # Invariance: assigned <= capacity for every shift
        for summary in result.shift_summaries:
            assert summary.assigned_count <= summary.capacity



class TestIntegrationWithScheduleAndPipelineResult:
    """Requirements 1 & 6: Chaining from ScheduleResult and PipelineResult."""

    def test_chaining_from_schedule_result(self, sample_fleet_df: pd.DataFrame) -> None:
        """ScheduleResult provides .plan_multi_shift() method."""
        probs = [0.95, 0.85, 0.75, 0.65, 0.30, 0.10]
        single_shift = plan_shift(sample_fleet_df, probabilities=probs, slots=1, threshold=0.50)

        # Re-plan into multi-shift from single shift plan
        multi_plan = single_shift.plan_multi_shift(shifts=[("Morning", 2), ("Afternoon", 1)])

        assert isinstance(multi_plan, MultiShiftPlanResult)
        assert multi_plan.shift_assignments["Morning"] == ["CNC-001", "CNC-002"]
        assert multi_plan.shift_assignments["Afternoon"] == ["CNC-003"]
        assert multi_plan.still_deferred_machines == ["CNC-004"]

    def test_chaining_from_pipeline_result_preserves_failure_modes(self) -> None:
        """PipelineResult provides .plan_multi_shift() preserving predicted_failure_mode."""
        telemetry_df = pd.DataFrame({
            "machine_id": ["CNC-001", "CNC-002", "CNC-003", "CNC-004"],
            "line": ["L1", "L1", "L2", "L2"],
        })
        y_val = [0, 0, 1, 1]
        p_val = [0.1, 0.2, 0.8, 0.9]

        mock_predict = lambda df: pd.DataFrame({
            "machine_id": df["machine_id"],
            "failure_probability": [0.94, 0.88, 0.82, 0.35],
            "predicted_failure_mode": ["Bearing Wear", "Overheating", "Tool Wear", "None"],
        })

        pipeline_res = predict_and_schedule(
            telemetry_df=telemetry_df,
            y_val=y_val,
            p_val=p_val,
            slots=1,
            predict_fn=mock_predict,
        )

        multi_plan = pipeline_res.plan_multi_shift(shifts=[("S1", 1), ("S2", 2)])

        assert multi_plan.shift_assignments["S1"] == ["CNC-001"]
        assert multi_plan.shift_assignments["S2"] == ["CNC-002", "CNC-003"]

        # Failure modes preserved
        tbl = multi_plan.assignments_table
        row1 = tbl[tbl["machine_id"] == "CNC-001"].iloc[0]
        assert row1["predicted_failure_mode"] == "Bearing Wear"
        row2 = tbl[tbl["machine_id"] == "CNC-002"].iloc[0]
        assert row2["predicted_failure_mode"] == "Overheating"
