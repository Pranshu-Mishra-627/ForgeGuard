"""Comprehensive test suite for Deferred-Machine Risk Management (engine/deferred_risk.py).

Tests:
1. Identification: only alerted machines unassigned due to capacity are deferred; non-alerted never deferred.
2. Ranking: descending priority score with deterministic alphanumeric tie-breaking.
3. Configurable escalation rules: Critical, High, Medium, Low risk tiers and customizable thresholds.
4. Follow-up recommendations: immediate supervisor review for critical, queue candidate for lower tiers,
   without silent slot assignment or assuming guaranteed next-shift dispatch.
5. Structured results: DataFrame and dataclass schemas, dictionary conversion, and explainability.
6. Validation and edge cases: zero slots, zero alerts, no deferred, tied priorities, invalid configs.
7. Integration: seamless interaction with ScheduleResult and PipelineResult.
"""

from __future__ import annotations

import pandas as pd
import pytest

from engine.cost_model import CostConfig
from engine.deferred_risk import (
    DEFAULT_RISK_TIER_CONFIG,
    DeferredMachineRisk,
    DeferredRiskResult,
    RiskTierConfig,
    evaluate_deferred_risk,
    manage_deferred_risk,
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


class TestDeferredIdentification:
    """Requirement 1: Strict identification of deferred machines."""

    def test_only_unassigned_alerts_are_deferred(self, sample_fleet_df: pd.DataFrame) -> None:
        """A machine must trigger the alert and not receive a technician slot to be deferred."""
        probs = [0.95, 0.85, 0.75, 0.65, 0.30, 0.10]
        # Threshold 0.50 -> CNC-001..004 alert (4 alerts). Slots = 2 -> CNC-001, CNC-002 selected.
        # CNC-003 and CNC-004 must be deferred. Non-alerted CNC-005, CNC-006 must NEVER be deferred.
        plan = plan_shift(df=sample_fleet_df, probabilities=probs, slots=2, threshold=0.50)

        deferred_res = evaluate_deferred_risk(plan)

        assert isinstance(deferred_res, DeferredRiskResult)
        assert deferred_res.deferred_count == 2
        deferred_ids = [m.machine_id for m in deferred_res.deferred_machines]
        assert deferred_ids == ["CNC-003", "CNC-004"]

        # Dispatched machines are NOT deferred
        assert "CNC-001" not in deferred_ids
        assert "CNC-002" not in deferred_ids

        # Non-alerted machines are NEVER deferred
        assert "CNC-005" not in deferred_ids
        assert "CNC-006" not in deferred_ids

    def test_non_alerted_machines_never_classified_as_deferred(self) -> None:
        """Direct DataFrame evaluation strictly excludes non-alerted machines."""
        direct_tbl = pd.DataFrame({
            "machine_id": ["M-A", "M-B", "M-C"],
            "failure_probability": [0.70, 0.20, 0.15],
            "alert": [True, False, False],
            "selected_for_service": [False, False, False],
            "priority_score": [14.0, 4.0, 3.0],
            "reason": ["Deferred", "Not alerted", "Not alerted"],
        })

        res = evaluate_deferred_risk(direct_tbl)
        assert res.deferred_count == 1
        assert res.deferred_machines[0].machine_id == "M-A"


class TestDeferredRankingAndTieBreaking:
    """Requirement 2: Deterministic risk ranking and tie-breaking."""

    def test_deferred_machines_ranked_by_descending_priority(self, sample_fleet_df: pd.DataFrame) -> None:
        """Deferred machines are strictly ordered by descending priority score."""
        probs = [0.90, 0.70, 0.80, 0.60, 0.10, 0.05]
        # Slots = 1 -> CNC-001 selected (prob 0.90)
        # Deferred: CNC-003 (0.80), CNC-002 (0.70), CNC-004 (0.60)
        plan = plan_shift(df=sample_fleet_df, probabilities=probs, slots=1, threshold=0.50)

        res = evaluate_deferred_risk(plan)
        deferred_ids = [m.machine_id for m in res.deferred_machines]
        assert deferred_ids == ["CNC-003", "CNC-002", "CNC-004"]

        # Check 1-indexed ranks
        assert res.deferred_machines[0].rank_among_deferred == 1
        assert res.deferred_machines[1].rank_among_deferred == 2
        assert res.deferred_machines[2].rank_among_deferred == 3

    def test_tied_priorities_broken_by_ascending_machine_id(self) -> None:
        """When priority scores are tied, ties break deterministically by ascending machine ID."""
        tied_df = pd.DataFrame({
            "machine_id": ["CNC-009", "CNC-002", "CNC-005"],
            "bay": ["A", "B", "C"],
        })
        probs = [0.75, 0.75, 0.75]  # Identical probabilities & priority scores
        plan = plan_shift(df=tied_df, probabilities=probs, slots=0, threshold=0.50)

        res = evaluate_deferred_risk(plan)
        deferred_ids = [m.machine_id for m in res.deferred_machines]
        # Alphanumeric ascending: CNC-002, CNC-005, CNC-009
        assert deferred_ids == ["CNC-002", "CNC-005", "CNC-009"]


class TestConfigurableEscalationRules:
    """Requirement 3: Configurable risk tiers and non-definitive failure phrasing."""

    def test_default_risk_tier_classification(self, sample_fleet_df: pd.DataFrame) -> None:
        """Categorizes into Critical (>=0.80), High (>=0.60), Medium (>=0.40), and Low (<0.40)."""
        probs = [0.95, 0.82, 0.65, 0.45, 0.25, 0.10]
        # Slots = 0, Threshold = 0.20 -> all 5 above 0.20 alert and are deferred
        plan = plan_shift(df=sample_fleet_df, probabilities=probs, slots=0, threshold=0.20)

        res = evaluate_deferred_risk(plan)

        tiers = {m.machine_id: m.risk_tier for m in res.deferred_machines}
        assert tiers["CNC-001"] == "Critical"  # 0.95 >= 0.80
        assert tiers["CNC-002"] == "Critical"  # 0.82 >= 0.80
        assert tiers["CNC-003"] == "High"      # 0.65 >= 0.60
        assert tiers["CNC-004"] == "Medium"    # 0.45 >= 0.40
        assert tiers["CNC-005"] == "Low"       # 0.25 < 0.40

        # Critical and High trigger escalation under default config
        assert res.deferred_machines[0].is_escalated is True
        assert res.deferred_machines[0].escalation_status == "Escalated"
        assert res.deferred_machines[2].is_escalated is True
        assert res.deferred_machines[3].is_escalated is False
        assert res.deferred_machines[3].escalation_status == "Standard Review"
        assert res.deferred_machines[4].is_escalated is False

    def test_custom_risk_tier_config(self, sample_fleet_df: pd.DataFrame) -> None:
        """Custom escalation thresholds operate independently of operational alert threshold."""
        probs = [0.88, 0.72, 0.55, 0.35, 0.20, 0.10]
        plan = plan_shift(df=sample_fleet_df, probabilities=probs, slots=1, threshold=0.30)

        # Custom config: Critical >= 0.85, High >= 0.70, Medium >= 0.50
        custom_cfg = RiskTierConfig(
            critical_threshold=0.85,
            high_threshold=0.70,
            medium_threshold=0.50,
            escalate_medium=True,  # also escalate medium
        )

        res = evaluate_deferred_risk(plan, config=custom_cfg)

        tiers = {m.machine_id: m.risk_tier for m in res.deferred_machines}
        assert tiers["CNC-002"] == "High"     # 0.72
        assert tiers["CNC-003"] == "Medium"   # 0.55
        assert tiers["CNC-004"] == "Low"      # 0.35

        # Medium was configured to escalate
        cnc3 = next(m for m in res.deferred_machines if m.machine_id == "CNC-003")
        assert cnc3.is_escalated is True
        assert cnc3.escalation_status == "Escalated"

    def test_calibrated_probabilistic_phrasing_never_claims_definite_failure(
        self, sample_fleet_df: pd.DataFrame
    ) -> None:
        """Explanations and recommendations use calibrated probabilistic language."""
        probs = [0.99, 0.90, 0.75, 0.50, 0.20, 0.10]
        plan = plan_shift(df=sample_fleet_df, probabilities=probs, slots=0, threshold=0.50)

        res = evaluate_deferred_risk(plan)
        for m in res.deferred_machines:
            # Must not claim definite failure
            assert "will definitely fail" not in m.reason.lower()
            assert "will fail" not in m.recommendation.lower()
            assert "certain to fail" not in m.reason.lower()


class TestFollowUpRecommendations:
    """Requirement 4: Actionable follow-up recommendations and policy boundaries."""

    def test_follow_up_recommendations_and_no_silent_slot_assignment(
        self, sample_fleet_df: pd.DataFrame
    ) -> None:
        """Critical deferred machines receive immediate supervisor review recommendation."""
        probs = [0.92, 0.84, 0.68, 0.48, 0.20, 0.10]
        # Slots = 1, Threshold = 0.45 -> CNC-001 selected; CNC-002, CNC-003, CNC-004 deferred
        plan = plan_shift(df=sample_fleet_df, probabilities=probs, slots=1, threshold=0.45)

        res = evaluate_deferred_risk(plan)

        critical_item = res.deferred_machines[0]  # CNC-002 (prob 0.84, Critical)
        assert critical_item.risk_tier == "Critical"
        assert "supervisor review" in critical_item.recommendation.lower()

        medium_item = res.deferred_machines[2]  # CNC-004 (prob 0.48, Medium)
        assert medium_item.risk_tier == "Medium"
        assert "candidate for evaluation in next shift planning" in medium_item.recommendation.lower()

        # Must NOT assume automatic next-shift assignment
        assert "automatically scheduled" not in medium_item.recommendation.lower()

        # Audit summary verifies current shift capacity was strictly respected
        assert res.selected_count == 1
        assert res.deferred_count == 3


class TestStructuredResultsAndExplain:
    """Requirement 5: Return structured results, DataFrame schemas, and explainability."""

    def test_structured_results_and_dataframe_schema(self, sample_fleet_df: pd.DataFrame) -> None:
        """Structured results contain all required fields and DataFrame columns."""
        probs = [0.90, 0.75, 0.65, 0.45, 0.20, 0.10]
        plan = plan_shift(df=sample_fleet_df, probabilities=probs, slots=1, threshold=0.40)

        res = evaluate_deferred_risk(plan)

        expected_cols = [
            "machine_id",
            "failure_probability",
            "priority_score",
            "risk_tier",
            "deferred_status",
            "escalation_status",
            "is_escalated",
            "recommendation",
            "reason",
            "rank_among_deferred",
            "predicted_failure_mode",
        ]
        assert list(res.risk_table.columns) == expected_cols
        assert len(res.risk_table) == res.deferred_count

        # Helper properties
        assert res.critical_machines == []
        assert res.high_risk_machines == ["CNC-002", "CNC-003"]
        assert res.escalated_machines == ["CNC-002", "CNC-003"]

        # Serialization to_dict()
        d = res.to_dict()
        assert "deferred_machines" in d
        assert "risk_table" in d
        assert "audit_summary" in d
        assert d["deferred_count"] == res.deferred_count

        # explain()
        explained = res.explain()
        assert "ForgeGuard Person 2 -- Deferred-Machine Risk & Escalation Report" in explained
        assert "CNC-002" in explained
        assert "CNC-003" in explained
        assert "[ESCALATED]" in explained


class TestValidationAndEdgeCases:
    """Requirement 6: Validation, edge cases, and robust error handling."""

    def test_edge_case_zero_technician_slots(self, sample_fleet_df: pd.DataFrame) -> None:
        """When zero slots available, all alerted machines are deferred and prioritized."""
        probs = [0.85, 0.70, 0.55, 0.30, 0.20, 0.10]
        plan = plan_shift(df=sample_fleet_df, probabilities=probs, slots=0, threshold=0.50)

        res = evaluate_deferred_risk(plan)
        assert res.selected_count == 0
        assert res.deferred_count == 3
        assert len(res.deferred_machines) == 3
        assert res.deferred_machines[0].machine_id == "CNC-001"

    def test_edge_case_no_alerts_triggered(self, sample_fleet_df: pd.DataFrame) -> None:
        """When no alerts triggered, deferred result is clean and empty without errors."""
        probs = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35]
        plan = plan_shift(df=sample_fleet_df, probabilities=probs, slots=3, threshold=0.50)

        res = evaluate_deferred_risk(plan)
        assert res.alerted_count == 0
        assert res.deferred_count == 0
        assert len(res.deferred_machines) == 0
        assert len(res.risk_table) == 0
        assert "No machines deferred" in res.explain()

    def test_edge_case_no_deferred_machines_capacity_exceeds_alerts(
        self, sample_fleet_df: pd.DataFrame
    ) -> None:
        """When capacity covers all alerts, deferred list is clean and empty."""
        probs = [0.90, 0.80, 0.30, 0.20, 0.10, 0.05]
        plan = plan_shift(df=sample_fleet_df, probabilities=probs, slots=5, threshold=0.50)

        res = evaluate_deferred_risk(plan)
        assert res.alerted_count == 2
        assert res.selected_count == 2
        assert res.deferred_count == 0
        assert res.deferred_machines == []
        assert len(res.risk_table) == 0

    def test_validation_rejects_invalid_risk_tier_configs(self) -> None:
        """Non-descending or out-of-bounds risk tier thresholds raise ValueError/TypeError."""
        # Non-descending thresholds: critical <= high
        with pytest.raises(ValueError, match="strictly descending"):
            RiskTierConfig(critical_threshold=0.60, high_threshold=0.70, medium_threshold=0.40)

        # High <= medium
        with pytest.raises(ValueError, match="strictly descending"):
            RiskTierConfig(critical_threshold=0.80, high_threshold=0.40, medium_threshold=0.40)

        # Thresholds out of [0, 1]
        with pytest.raises(ValueError, match="bounded in"):
            RiskTierConfig(critical_threshold=1.20)

        with pytest.raises(ValueError, match="bounded in"):
            RiskTierConfig(medium_threshold=-0.10)

        # Non-numeric threshold
        with pytest.raises(TypeError, match="must be numeric"):
            RiskTierConfig(critical_threshold="high")  # type: ignore

    def test_validation_rejects_invalid_input_objects(self) -> None:
        """Passing non-ScheduleResult/DataFrame objects raises TypeError."""
        with pytest.raises(TypeError, match="must be a ScheduleResult, PipelineResult, or DataFrame"):
            evaluate_deferred_risk("invalid_string_input")

        with pytest.raises(TypeError, match="must be a ScheduleResult, PipelineResult, or DataFrame"):
            evaluate_deferred_risk([1, 2, 3])

    def test_validation_rejects_invalid_probabilities_and_missing_columns(self) -> None:
        """DataFrames with invalid probabilities or missing columns are rejected."""
        # Missing columns
        bad_df = pd.DataFrame({"machine_id": ["M-1"], "failure_probability": [0.8]})
        with pytest.raises(ValueError, match="missing required scheduler columns"):
            evaluate_deferred_risk(bad_df)

        # Invalid probability > 1.0
        bad_prob_df = pd.DataFrame({
            "machine_id": ["M-1"],
            "failure_probability": [1.5],
            "alert": [True],
            "selected_for_service": [False],
            "priority_score": [15.0],
            "reason": ["Deferred"],
        })
        with pytest.raises(ValueError, match="finite and in"):
            evaluate_deferred_risk(bad_prob_df)

        # NaN probability
        nan_prob_df = pd.DataFrame({
            "machine_id": ["M-1"],
            "failure_probability": [float("nan")],
            "alert": [True],
            "selected_for_service": [False],
            "priority_score": [15.0],
            "reason": ["Deferred"],
        })
        with pytest.raises(ValueError, match="finite and in"):
            evaluate_deferred_risk(nan_prob_df)

        # DeferredMachineRisk constructor validation
        with pytest.raises(ValueError, match="finite and in"):
            DeferredMachineRisk(
                machine_id="M-1",
                failure_probability=-0.2,
                priority_score=10.0,
                risk_tier="High",
                deferred_status=True,
                escalation_status="Escalated",
                is_escalated=True,
                recommendation="Review",
                reason="High risk",
            )

    def test_assigned_machines_never_escalated(self, sample_fleet_df: pd.DataFrame) -> None:
        """Machines assigned to slots are never classified as deferred or escalated."""
        probs = [0.99, 0.95, 0.40, 0.30, 0.20, 0.10]
        # Slots = 2: CNC-001 (0.99) and CNC-002 (0.95) are selected for service
        # They have Critical risk probabilities, but because they have technician slots,
        # they must NEVER be classified as deferred or escalated.
        plan = plan_shift(df=sample_fleet_df, probabilities=probs, slots=2, threshold=0.50)
        res = evaluate_deferred_risk(plan)

        assert res.deferred_count == 0
        assert res.escalated_count == 0
        assert res.critical_machines == []
        assert res.escalated_machines == []
        assert "CNC-001" not in [m.machine_id for m in res.deferred_machines]
        assert "CNC-002" not in [m.machine_id for m in res.deferred_machines]



class TestIntegrationWithSchedulerAndPipeline:
    """Requirement 7: Seamless integration with ScheduleResult and PipelineResult."""

    def test_schedule_result_evaluate_deferred_risk_helper(
        self, sample_fleet_df: pd.DataFrame
    ) -> None:
        """ScheduleResult provides evaluate_deferred_risk() and deferred_risk property."""
        probs = [0.95, 0.85, 0.65, 0.30, 0.20, 0.10]
        plan = plan_shift(df=sample_fleet_df, probabilities=probs, slots=1, threshold=0.50)

        # Via method
        res1 = plan.evaluate_deferred_risk()
        assert isinstance(res1, DeferredRiskResult)
        assert res1.deferred_count == 2

        # Via property
        res2 = plan.deferred_risk
        assert isinstance(res2, DeferredRiskResult)
        assert res2.deferred_count == 2

        # Standard alias manage_deferred_risk
        res3 = manage_deferred_risk(plan)
        assert res3.deferred_count == 2

    def test_pipeline_result_integration_preserves_failure_modes(self) -> None:
        """PipelineResult integration preserves predicted_failure_mode in deferred risk table."""
        telemetry_df = pd.DataFrame({
            "machine_id": ["CNC-001", "CNC-002", "CNC-003", "CNC-004"],
            "line": ["L1", "L1", "L2", "L2"],
        })
        y_val = [0, 0, 1, 1]
        p_val = [0.1, 0.2, 0.8, 0.9]

        mock_predict = lambda df: pd.DataFrame({
            "machine_id": df["machine_id"],
            "failure_probability": [0.92, 0.86, 0.82, 0.35],
            "predicted_failure_mode": ["Bearing Wear", "Overheating", "Tool Wear", "None"],
        })

        pipeline_res = predict_and_schedule(
            telemetry_df=telemetry_df,
            y_val=y_val,
            p_val=p_val,
            slots=1,
            predict_fn=mock_predict,
        )

        deferred_res = pipeline_res.evaluate_deferred_risk()
        assert isinstance(deferred_res, DeferredRiskResult)
        assert deferred_res.deferred_count == 2  # CNC-002 (0.84) and CNC-003 (0.72)

        # Verify predicted_failure_mode preserved
        cnc2 = next(m for m in deferred_res.deferred_machines if m.machine_id == "CNC-002")
        assert cnc2.predicted_failure_mode == "Overheating"

        cnc3 = next(m for m in deferred_res.deferred_machines if m.machine_id == "CNC-003")
        assert cnc3.predicted_failure_mode == "Tool Wear"

        # Property access on PipelineResult
        assert pipeline_res.deferred_risk is not None
        assert pipeline_res.deferred_risk.deferred_count == 2
