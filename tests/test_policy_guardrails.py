"""Comprehensive test suite for Maintenance Policy Guardrails (engine/policy_guardrails.py).

Tests:
1. Configurable Policies: Risk tiers, mandatory review, escalation for deferred assets, max deferral limits.
2. Guardrail Evaluation: policy_triggered, requires_human_review, escalation_required, policy_reason,
   and distinction between violations, escalations, reviews, and normal deferrals.
3. Capacity & Safety: Guardrails never silently exceed technician capacity or alter scheduled dispatches.
4. Deferral Tracking: Real deferral history evaluated; no fabricated past shifts when history is absent;
   max consecutive deferrals violation.
5. Structured Results & Schemas: MachineGuardrailRecord, guardrail_table DataFrame, to_dict(), explain().
6. Deterministic Precedence: Severity-based resolution of multiple simultaneous policy triggers.
7. Validation & Edge Cases: Empty fleet, no alerts, zero capacity, invalid configs, non-numeric inputs.
8. Integration: Seamless evaluation on ScheduleResult, MultiShiftPlanResult, and PipelineResult.
"""

from __future__ import annotations

import pandas as pd
import pytest

from engine.deferred_risk import RiskTierConfig
from engine.multi_shift_scheduler import ShiftConfig, plan_multi_shift
from engine.pipeline import predict_and_schedule
from engine.policy_guardrails import (
    DEFAULT_POLICY_CONFIG,
    POLICY_COMPLIANT,
    POLICY_CRITICAL_ALERT,
    POLICY_CRITICAL_DEFERRED,
    POLICY_HIGH_DEFERRED,
    POLICY_MAX_DEFERRALS_EXCEEDED,
    POLICY_MEDIUM_DEFERRED,
    POLICY_STANDARD_DEFERRAL,
    VIOLATION_TYPE_COMPLIANT,
    VIOLATION_TYPE_ESCALATION_RECOMMENDED,
    VIOLATION_TYPE_MANDATORY_REVIEW,
    VIOLATION_TYPE_NORMAL_DEFERRAL,
    VIOLATION_TYPE_POLICY_VIOLATION,
    MachineGuardrailRecord,
    MaintenancePolicyConfig,
    PolicyGuardrailResult,
    evaluate_guardrails,
)
from engine.scheduler import plan_shift


@pytest.fixture
def sample_fleet_df() -> pd.DataFrame:
    """Standard 6-machine fleet DataFrame."""
    return pd.DataFrame({
        "machine_id": ["CNC-001", "CNC-002", "CNC-003", "CNC-004", "CNC-005", "CNC-006"],
        "bay": ["A", "A", "B", "B", "C", "C"],
    })


class TestConfigurableMaintenancePolicies:
    """Requirement 1: Configurable risk tiers, mandatory review, and deferral ceilings."""

    def test_default_policy_assumptions(self) -> None:
        """Default policy assumptions match documented specifications."""
        cfg = DEFAULT_POLICY_CONFIG
        assert isinstance(cfg, MaintenancePolicyConfig)
        assert cfg.mandatory_review_critical is True
        assert cfg.escalate_critical_deferred is True
        assert cfg.escalate_high_deferred is True
        assert cfg.max_consecutive_deferrals == 2
        assert cfg.enforce_max_deferral_violation is True

    def test_custom_policy_configuration(self, sample_fleet_df: pd.DataFrame) -> None:
        """Custom policy configuration allows tuning thresholds and flags independently."""
        custom_cfg = MaintenancePolicyConfig(
            risk_config=RiskTierConfig(critical_threshold=0.85, high_threshold=0.65, medium_threshold=0.45),
            mandatory_review_critical=False,
            max_consecutive_deferrals=3,
        )
        assert custom_cfg.max_consecutive_deferrals == 3
        assert custom_cfg.mandatory_review_critical is False
        assert custom_cfg.risk_config.critical_threshold == 0.85


class TestGuardrailEvaluationAndDistinctions:
    """Requirement 2: Explicit guardrail results, distinctions, and calibrated phrasing."""

    def test_distinguish_violation_escalation_review_and_normal_deferral(
        self, sample_fleet_df: pd.DataFrame
    ) -> None:
        """Distinguishes POLICY_VIOLATION, ESCALATION_RECOMMENDED, MANDATORY_REVIEW, NORMAL_DEFERRAL, COMPLIANT."""
        probs = [0.95, 0.82, 0.65, 0.45, 0.20, 0.10]
        # Slots = 1, Threshold = 0.40 -> CNC-001 dispatched; CNC-002, CNC-003, CNC-004 deferred.
        schedule = plan_shift(df=sample_fleet_df, probabilities=probs, slots=1, threshold=0.40)
        res = evaluate_guardrails(schedule)

        records_by_id = {r.machine_id: r for r in res.records}

        # CNC-001: Dispatched, but prob=0.95 (Critical risk) -> MANDATORY_REVIEW
        r1 = records_by_id["CNC-001"]
        assert r1.selected_for_service is True
        assert r1.requires_human_review is True
        assert r1.violation_type == VIOLATION_TYPE_MANDATORY_REVIEW
        assert r1.primary_policy_id == POLICY_CRITICAL_ALERT

        # CNC-002: Deferred, prob=0.82 (Critical risk) -> POLICY_VIOLATION (Critical asset left unserviced)
        r2 = records_by_id["CNC-002"]
        assert r2.selected_for_service is False
        assert r2.is_violation is True
        assert r2.violation_type == VIOLATION_TYPE_POLICY_VIOLATION
        assert r2.primary_policy_id == POLICY_CRITICAL_DEFERRED
        assert r2.escalation_required is True
        assert r2.requires_human_review is True

        # CNC-003: Deferred, prob=0.65 (High risk) -> ESCALATION_RECOMMENDED
        r3 = records_by_id["CNC-003"]
        assert r3.selected_for_service is False
        assert r3.is_violation is False
        assert r3.violation_type == VIOLATION_TYPE_ESCALATION_RECOMMENDED
        assert r3.primary_policy_id == POLICY_HIGH_DEFERRED
        assert r3.escalation_required is True

        # CNC-004: Deferred, prob=0.45 (Medium risk) -> NORMAL_DEFERRAL
        r4 = records_by_id["CNC-004"]
        assert r4.selected_for_service is False
        assert r4.violation_type == VIOLATION_TYPE_NORMAL_DEFERRAL
        assert r4.primary_policy_id == POLICY_MEDIUM_DEFERRED

        # CNC-005: Unalerted, prob=0.20 -> COMPLIANT
        r5 = records_by_id["CNC-005"]
        assert r5.policy_triggered is False
        assert r5.violation_type == VIOLATION_TYPE_COMPLIANT
        assert r5.primary_policy_id == POLICY_COMPLIANT

    def test_calibrated_probabilistic_phrasing_never_claims_certain_failure(
        self, sample_fleet_df: pd.DataFrame
    ) -> None:
        """Policy explanations strictly use calibrated probabilistic language without asserting certainty."""
        probs = [0.99, 0.90, 0.75, 0.50, 0.20, 0.10]
        schedule = plan_shift(df=sample_fleet_df, probabilities=probs, slots=0, threshold=0.50)
        res = evaluate_guardrails(schedule)

        for r in res.records:
            reason_lower = r.policy_reason.lower()
            assert "will definitely fail" not in reason_lower
            assert "will fail" not in reason_lower
            assert "certain to fail" not in reason_lower


class TestCapacityAndSchedulingSafety:
    """Requirement 3: Guardrails never silently exceed capacity or alter dispatches."""

    def test_guardrails_never_alter_technician_capacity_or_slots(
        self, sample_fleet_df: pd.DataFrame
    ) -> None:
        """Triggered guardrails recommend urgent action but never silently add slots or alter assignments."""
        probs = [0.95, 0.90, 0.85, 0.50, 0.20, 0.10]
        # 3 critical machines alert, but only 1 slot is available
        schedule = plan_shift(df=sample_fleet_df, probabilities=probs, slots=1, threshold=0.50)

        # Before guardrails: CNC-001 selected, others deferred
        assert schedule.selected_machines == ["CNC-001"]
        assert len(schedule.deferred_machines) == 3

        res = evaluate_guardrails(schedule)

        # Guardrails report 2 severe violations
        assert res.violation_count == 2
        assert "CNC-002" in res.violations
        assert "CNC-003" in res.violations

        # Dispatched count strictly preserved at 1 (no silent extra slot)
        assert res.dispatched_count == 1
        assert res.deferred_count == 3
        # CNC-002 and CNC-003 are still not selected
        assert res.records[1].selected_for_service is False
        assert res.records[2].selected_for_service is False


class TestDeferralTrackingAndCeilings:
    """Requirement 4: Deferral history tracking and maximum consecutive deferral enforcement."""

    def test_max_consecutive_deferrals_exceeded_in_multi_shift(
        self, sample_fleet_df: pd.DataFrame
    ) -> None:
        """When a machine reaches or exceeds max_consecutive_deferrals, it triggers POL_MAX_DEFERRALS_EXCEEDED."""
        probs = [0.90, 0.80, 0.70, 0.60, 0.20, 0.10]
        # 3 shifts with capacity 1 each.
        # CNC-001 gets Shift 1, CNC-002 gets Shift 2, CNC-003 gets Shift 3.
        # CNC-004 is deferred in Shift 1, Shift 2, Shift 3 -> 3 consecutive deferrals!
        shifts = [("S1", 1), ("S2", 1), ("S3", 1)]
        multi_plan = plan_multi_shift(sample_fleet_df, shifts, probabilities=probs, threshold=0.50)

        # Guardrail with max_consecutive_deferrals = 2
        cfg = MaintenancePolicyConfig(max_consecutive_deferrals=2)
        guardrails = multi_plan.evaluate_guardrails(config=cfg)

        cnc4 = next(r for r in guardrails.records if r.machine_id == "CNC-004")
        assert cnc4.consecutive_deferrals == 3
        assert cnc4.is_violation is True
        assert cnc4.violation_type == VIOLATION_TYPE_POLICY_VIOLATION
        assert cnc4.primary_policy_id == POLICY_MAX_DEFERRALS_EXCEEDED
        assert "Consecutive deferral limit (2 shifts) reached or exceeded" in cnc4.policy_reason

    def test_absent_deferral_history_not_fabricated(self, sample_fleet_df: pd.DataFrame) -> None:
        """When no deferral history is present (e.g. raw single shift), do not invent past shifts."""
        probs = [0.90, 0.60, 0.50, 0.40, 0.20, 0.10]
        # Raw fleet table evaluation without historical shifts
        direct_tbl = pd.DataFrame({
            "machine_id": ["M-1", "M-2"],
            "failure_probability": [0.70, 0.20],
            "alert": [True, False],
            "selected_for_service": [False, False],
            "priority_score": [14.0, 4.0],
            "reason": ["Deferred", "Not alerted"],
        })
        res = evaluate_guardrails(direct_tbl)
        m1 = res.records[0]
        # Counted as 1 current deferral, not fabricated past shifts
        assert m1.consecutive_deferrals == 1
        assert m1.primary_policy_id == POLICY_HIGH_DEFERRED


class TestDeterministicPolicyPrecedence:
    """Requirement 6: Deterministic policy precedence hierarchy."""

    def test_precedence_max_deferral_over_critical_deferred(self) -> None:
        """POL_MAX_DEFERRALS_EXCEEDED takes precedence over POL_CRITICAL_DEFERRED when both apply."""
        # A machine with prob=0.95 (Critical), deferred, and 3 consecutive deferrals
        df = pd.DataFrame({
            "machine_id": ["M-CRIT-DEF"],
            "failure_probability": [0.95],
            "priority_score": [19.0],
            "alert": [True],
            "selected_for_service": [False],
            "deferral_history": [["S1", "S2", "S3"]],
            "reason": ["Deferred across S1, S2, S3"],
        })
        cfg = MaintenancePolicyConfig(max_consecutive_deferrals=2)
        res = evaluate_guardrails(df, config=cfg)

        rec = res.records[0]
        # Both policies apply: POL_MAX_DEFERRALS_EXCEEDED (100) > POL_CRITICAL_DEFERRED (90)
        assert rec.primary_policy_id == POLICY_MAX_DEFERRALS_EXCEEDED
        assert rec.triggered_policies == [
            POLICY_MAX_DEFERRALS_EXCEEDED,
            POLICY_CRITICAL_DEFERRED,
            POLICY_CRITICAL_ALERT,
        ]
        assert rec.is_violation is True


class TestStructuredResultsAndExplain:
    """Requirement 5: Structured outputs, DataFrame schemas, to_dict(), and explain()."""

    def test_structured_results_and_dataframe_schema(self, sample_fleet_df: pd.DataFrame) -> None:
        """Guardrail table contains all expected columns and audit properties."""
        probs = [0.92, 0.85, 0.60, 0.45, 0.20, 0.10]
        schedule = plan_shift(df=sample_fleet_df, probabilities=probs, slots=1, threshold=0.40)
        res = evaluate_guardrails(schedule)

        expected_cols = [
            "machine_id",
            "failure_probability",
            "priority_score",
            "risk_tier",
            "alert",
            "selected_for_service",
            "assigned_shift",
            "still_deferred",
            "consecutive_deferrals",
            "policy_triggered",
            "requires_human_review",
            "escalation_required",
            "is_violation",
            "violation_type",
            "primary_policy_id",
            "policy_reason",
            "original_reason",
        ]
        for col in expected_cols:
            assert col in res.guardrail_table.columns

        # Properties
        assert len(res.violations) == res.violation_count
        assert len(res.review_required_machines) == res.human_review_count
        assert len(res.escalated_machines) == res.escalation_count

        # to_dict()
        d = res.to_dict()
        assert "records" in d
        assert "guardrail_table" in d
        assert "audit_summary" in d
        assert d["total_fleet_count"] == 6

        # explain()
        explained = res.explain()
        assert "Maintenance Policy Guardrail Audit" in explained
        assert "CRITICAL POLICY VIOLATIONS" in explained
        assert "CNC-002" in explained


class TestValidationAndEdgeCases:
    """Requirement 6: Validation, edge cases, and robust error handling."""

    def test_edge_case_empty_dataframe(self) -> None:
        """Empty fleet DataFrame returns clean empty result without errors."""
        empty_df = pd.DataFrame(columns=["machine_id", "failure_probability"])
        res = evaluate_guardrails(empty_df)
        assert res.total_fleet_count == 0
        assert res.policy_triggered_count == 0
        assert len(res.records) == 0
        assert len(res.guardrail_table) == 0

    def test_edge_case_no_alerts_triggered(self, sample_fleet_df: pd.DataFrame) -> None:
        """When no alerts trigger, all machines are compliant with zero policy triggers."""
        probs = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35]
        schedule = plan_shift(sample_fleet_df, probabilities=probs, slots=2, threshold=0.50)
        res = evaluate_guardrails(schedule)

        assert res.alerted_count == 0
        assert res.policy_triggered_count == 0
        assert res.violation_count == 0
        assert "fully compliant" in res.explain()

    def test_edge_case_zero_technician_capacity(self, sample_fleet_df: pd.DataFrame) -> None:
        """When zero slots available, all alerts are deferred and guardrails evaluate properly."""
        probs = [0.85, 0.70, 0.55, 0.30, 0.20, 0.10]
        schedule = plan_shift(sample_fleet_df, probabilities=probs, slots=0, threshold=0.50)
        res = evaluate_guardrails(schedule)

        assert res.dispatched_count == 0
        assert res.deferred_count == 3
        # CNC-001 (0.85) is Critical deferred -> Violation
        assert res.records[0].is_violation is True

    def test_validation_rejects_invalid_configurations(self) -> None:
        """Invalid policy configurations raise TypeError or ValueError."""
        # max_consecutive_deferrals < 1
        with pytest.raises(ValueError, match="at least 1"):
            MaintenancePolicyConfig(max_consecutive_deferrals=0)

        # Non-integer max_consecutive_deferrals
        with pytest.raises(TypeError, match="must be an integer"):
            MaintenancePolicyConfig(max_consecutive_deferrals=2.5)  # type: ignore

        with pytest.raises(TypeError, match="must be an integer"):
            MaintenancePolicyConfig(max_consecutive_deferrals=True)  # type: ignore

        # Invalid risk_config
        with pytest.raises(TypeError, match="RiskTierConfig"):
            MaintenancePolicyConfig(risk_config="invalid")  # type: ignore

    def test_validation_rejects_invalid_probabilities(self) -> None:
        """Probabilities outside [0.0, 1.0] or non-finite raise ValueError."""
        bad_df = pd.DataFrame({
            "machine_id": ["M-1"],
            "failure_probability": [1.5],
            "alert": [True],
            "selected_for_service": [False],
        })
        with pytest.raises(ValueError, match="finite and in"):
            evaluate_guardrails(bad_df)


class TestIntegrationWithEngineModules:
    """Requirement 7: Integration with ScheduleResult, MultiShiftPlanResult, and PipelineResult."""

    def test_schedule_result_helper_and_property(self, sample_fleet_df: pd.DataFrame) -> None:
        """ScheduleResult provides evaluate_guardrails() method and .guardrails property."""
        probs = [0.95, 0.80, 0.60, 0.40, 0.20, 0.10]
        sched = plan_shift(sample_fleet_df, probabilities=probs, slots=1, threshold=0.50)

        # Via method
        res1 = sched.evaluate_guardrails()
        assert isinstance(res1, PolicyGuardrailResult)
        assert res1.total_fleet_count == 6

        # Via property
        res2 = sched.guardrails
        assert isinstance(res2, PolicyGuardrailResult)
        assert res2.total_fleet_count == 6

    def test_multi_shift_plan_result_helper_and_property(
        self, sample_fleet_df: pd.DataFrame
    ) -> None:
        """MultiShiftPlanResult provides evaluate_guardrails() method and .guardrails property."""
        probs = [0.90, 0.80, 0.70, 0.60, 0.20, 0.10]
        multi_plan = plan_multi_shift(
            sample_fleet_df, [("S1", 1), ("S2", 1)], probabilities=probs, threshold=0.50
        )

        res = multi_plan.evaluate_guardrails()
        assert isinstance(res, PolicyGuardrailResult)
        assert res.total_fleet_count == 6
        assert multi_plan.guardrails is not None

    def test_pipeline_result_helper_and_property_preserves_failure_modes(self) -> None:
        """PipelineResult integration preserves ML predicted_failure_mode in guardrail records."""
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

        guardrails = pipeline_res.evaluate_guardrails()
        assert isinstance(guardrails, PolicyGuardrailResult)

        # Check failure mode preserved
        cnc1 = next(r for r in guardrails.records if r.machine_id == "CNC-001")
        assert cnc1.predicted_failure_mode == "Bearing Wear"
        cnc2 = next(r for r in guardrails.records if r.machine_id == "CNC-002")
        assert cnc2.predicted_failure_mode == "Overheating"

        assert pipeline_res.guardrails is not None
