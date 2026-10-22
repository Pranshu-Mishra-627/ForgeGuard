"""Unit tests for ForgeGuard Preemptive Maintenance Scheduling (engine/preemption.py).

Verifies all 15 required scenarios:
1. Incoming priority clearly exceeds current job priority and preemption is allowed.
2. Incoming priority is lower or equal; no preemption occurs.
3. Configured minimum priority margin is not met.
4. Current job is not interruptible (explicit flag or non-interruptible job type).
5. Safety or interruptibility metadata is missing (denied for safety and escalated).
6. Human approval is required but not yet granted (pending_approval, job preserved).
7. Human approval is granted and preemption executes.
8. Technician capacity and single-active-job invariant are preserved.
9. Interrupted job progress/state is preserved for later rescheduling.
10. Existing assignments for other technicians remain unchanged.
11. Duplicate or repeated preemption attempts are handled safely.
12. Guardrails block unauthorized preemption (mandatory review enforcement).
13. Actual failure and predicted-risk alerts follow configured policies.
14. Deterministic decisions, explanations, and invalid configuration handling.
15. Integration with ScheduleResult and PipelineResult.
"""

from __future__ import annotations

import math
import pytest
import pandas as pd
import numpy as np

from engine.preemption import (
    ALERT_CATEGORY_ACTUAL_FAILURE,
    ALERT_CATEGORY_CRITICAL_ALERT,
    ALERT_CATEGORY_PREDICTED_HIGH_RISK,
    ALERT_CATEGORY_ROUTINE,
    DEFAULT_PREEMPTION_CONFIG,
    JOB_STATUS_ACTIVE,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_DISPATCHED,
    JOB_STATUS_IN_PROGRESS,
    JOB_STATUS_INTERRUPTED,
    JOB_STATUS_PAUSED,
    JOB_STATUS_PENDING,
    STATUS_DENIED,
    STATUS_EXECUTED,
    STATUS_NO_PREEMPTION,
    STATUS_PENDING_APPROVAL,
    STATUS_RECOMMENDED,
    MaintenanceJob,
    PreemptionConfig,
    PreemptionManager,
    PreemptionResult,
    TechnicianAssignment,
    evaluate_preemption,
    execute_preemption,
)
from engine.policy_guardrails import (
    DEFAULT_POLICY_CONFIG,
    MaintenancePolicyConfig,
    RiskTierConfig,
)
from engine.scheduler import plan_shift
from engine.pipeline import run_pipeline


class TestPreemptionPriorityAndEligibility:
    """Tests evaluating priority comparison, margins, and alert category rules."""

    def test_scenario_1_incoming_priority_exceeds_current_and_preemption_executes(self) -> None:
        """Scenario 1: Incoming priority clearly exceeds current job and preemption executes."""
        current_job = MaintenanceJob(
            job_id="JOB-C",
            machine_id="CNC-03",
            priority_score=18.0,
            status=JOB_STATUS_IN_PROGRESS,
            job_type="preventive_maintenance",
            is_interruptible=True,
            technician_id="TECH-01",
            progress=0.45,
        )
        incoming_job = MaintenanceJob(
            job_id="JOB-A",
            machine_id="PRESS-01",
            priority_score=95.0,
            alert_category=ALERT_CATEGORY_ACTUAL_FAILURE,
        )

        # 1. Non-mutating evaluation
        eval_res = evaluate_preemption(current_job, incoming_job, technician_id="TECH-01")
        assert eval_res.preemption_considered is True
        assert eval_res.preemption_executed is True
        assert eval_res.requires_human_approval is False
        assert eval_res.status == STATUS_EXECUTED
        assert eval_res.interrupted_job_id == "JOB-C"
        assert eval_res.incoming_job_id == "JOB-A"
        assert eval_res.current_priority_score == 18.0
        assert eval_res.incoming_priority_score == 95.0
        assert "Actual machine breakdown failure" in eval_res.decision_reason
        assert eval_res.interrupted_job_status == JOB_STATUS_INTERRUPTED

        # Verify evaluation did not mutate original job state
        assert current_job.status == JOB_STATUS_IN_PROGRESS

        # 2. Execution with state mutation
        exec_res, paused_job, new_job = execute_preemption(
            current_job, incoming_job, technician_id="TECH-01", timestamp="2026-10-22T12:00:00Z"
        )
        assert exec_res.preemption_executed is True
        assert paused_job.status == JOB_STATUS_INTERRUPTED
        assert paused_job.progress == 0.45  # preserved
        assert paused_job.interrupted_at == "2026-10-22T12:00:00Z"
        assert paused_job.preempted_by_job_id == "JOB-A"
        assert new_job.status == JOB_STATUS_IN_PROGRESS
        assert new_job.technician_id == "TECH-01"

    def test_scenario_2_incoming_priority_lower_or_equal_denied(self) -> None:
        """Scenario 2: Incoming priority is lower or equal; no preemption occurs."""
        current_job = MaintenanceJob(
            job_id="JOB-ACTIVE",
            machine_id="M-01",
            priority_score=75.0,
            status=JOB_STATUS_IN_PROGRESS,
            is_interruptible=True,
        )

        # Lower priority
        incoming_lower = MaintenanceJob(
            job_id="JOB-LOWER",
            machine_id="M-02",
            priority_score=50.0,
            alert_category=ALERT_CATEGORY_PREDICTED_HIGH_RISK,
        )
        res_lower = evaluate_preemption(current_job, incoming_lower)
        assert res_lower.preemption_executed is False
        assert res_lower.status == STATUS_DENIED
        assert "does not exceed" in res_lower.decision_reason
        assert res_lower.recommended_action == "Maintain current technician assignment."

        # Equal priority
        incoming_equal = MaintenanceJob(
            job_id="JOB-EQUAL",
            machine_id="M-03",
            priority_score=75.0,
            alert_category=ALERT_CATEGORY_PREDICTED_HIGH_RISK,
        )
        res_equal = evaluate_preemption(current_job, incoming_equal)
        assert res_equal.preemption_executed is False
        assert res_equal.status == STATUS_DENIED
        assert "does not exceed" in res_equal.decision_reason

    def test_scenario_3_min_priority_margin_not_met(self) -> None:
        """Scenario 3: Configured minimum priority margin is not met."""
        config = PreemptionConfig(min_priority_delta=15.0)

        current_job = MaintenanceJob(
            job_id="JOB-1",
            machine_id="M-01",
            priority_score=50.0,
            is_interruptible=True,
        )
        # Margin is 10.0, but 15.0 is required
        incoming_job = MaintenanceJob(
            job_id="JOB-2",
            machine_id="M-02",
            priority_score=60.0,
            alert_category=ALERT_CATEGORY_PREDICTED_HIGH_RISK,
        )

        res = evaluate_preemption(current_job, incoming_job, config=config)
        assert res.preemption_executed is False
        assert res.status == STATUS_DENIED
        assert "Priority margin (10.00) does not meet the configured minimum priority delta (15.00)" in res.decision_reason

        # When margin is 15.0 or greater, it succeeds
        incoming_high = MaintenanceJob(
            job_id="JOB-3",
            machine_id="M-03",
            priority_score=65.0,
            alert_category=ALERT_CATEGORY_PREDICTED_HIGH_RISK,
        )
        res_ok = evaluate_preemption(current_job, incoming_high, config=config)
        assert res_ok.preemption_executed is True
        assert res_ok.status == STATUS_EXECUTED

    def test_scenario_13_actual_failure_vs_predicted_risk_alert_categories(self) -> None:
        """Scenario 13: Actual failure and predicted-risk alerts follow configured policies."""
        # Config allows only actual failures to trigger preemption
        config = PreemptionConfig(allowed_alert_categories=(ALERT_CATEGORY_ACTUAL_FAILURE,))

        current_job = MaintenanceJob(
            job_id="JOB-ACTIVE",
            machine_id="M-01",
            priority_score=20.0,
            is_interruptible=True,
        )

        # Predicted high-risk alert is denied under this configuration
        predicted_alert = MaintenanceJob(
            job_id="JOB-PRED",
            machine_id="M-02",
            priority_score=90.0,
            failure_probability=0.95,
            alert_category=ALERT_CATEGORY_PREDICTED_HIGH_RISK,
        )
        res_pred = evaluate_preemption(current_job, predicted_alert, config=config)
        assert res_pred.preemption_executed is False
        assert res_pred.status == STATUS_DENIED
        assert "not permitted to trigger preemption" in res_pred.decision_reason

        # Actual breakdown failure is permitted
        breakdown_alert = MaintenanceJob(
            job_id="JOB-BREAKDOWN",
            machine_id="M-03",
            priority_score=90.0,
            alert_category=ALERT_CATEGORY_ACTUAL_FAILURE,
        )
        res_act = evaluate_preemption(current_job, breakdown_alert, config=config)
        assert res_act.preemption_executed is True
        assert res_act.status == STATUS_EXECUTED
        assert "Actual machine breakdown failure" in res_act.decision_reason


class TestInterruptibilityAndSafety:
    """Tests verifying safe interruptibility rules, metadata verification, and safety fallbacks."""

    def test_scenario_4_current_job_marked_non_interruptible(self) -> None:
        """Scenario 4: Current job is explicitly marked non-interruptible."""
        current_job = MaintenanceJob(
            job_id="JOB-CRIT",
            machine_id="M-01",
            priority_score=20.0,
            is_interruptible=False,  # Explicitly non-interruptible
        )
        incoming_job = MaintenanceJob(
            job_id="JOB-URGENT",
            machine_id="M-02",
            priority_score=95.0,
        )

        res = evaluate_preemption(current_job, incoming_job)
        assert res.preemption_executed is False
        assert res.status == STATUS_DENIED
        assert "explicitly marked non-interruptible" in res.decision_reason
        assert res.requires_human_approval is True  # Escalates for supervisor awareness

    def test_scenario_4_safety_critical_job_type_non_interruptible(self) -> None:
        """Scenario 4: Work type is safety-critical (e.g. hazardous material or emergency repair)."""
        current_job = MaintenanceJob(
            job_id="JOB-HAZ",
            machine_id="M-01",
            priority_score=20.0,
            job_type="hazardous_material_service",
            is_interruptible=True,  # Even if mistakenly set to True, safety list blocks it
        )
        incoming_job = MaintenanceJob(
            job_id="JOB-URGENT",
            machine_id="M-02",
            priority_score=95.0,
        )

        res = evaluate_preemption(current_job, incoming_job)
        assert res.preemption_executed is False
        assert res.status == STATUS_DENIED
        assert "non-interruptible safety list" in res.decision_reason

    def test_scenario_5_missing_safety_metadata_denies_and_escalates(self) -> None:
        """Scenario 5: Safety or interruptibility metadata is missing; denied and escalated."""
        config = PreemptionConfig(allow_unknown_interruptibility=False)

        current_job = MaintenanceJob(
            job_id="JOB-UNKNOWN",
            machine_id="M-01",
            priority_score=15.0,
            job_type="custom_unclassified_procedure",
            is_interruptible=None,  # Missing explicit metadata
        )
        incoming_job = MaintenanceJob(
            job_id="JOB-URGENT",
            machine_id="M-02",
            priority_score=90.0,
        )

        res = evaluate_preemption(current_job, incoming_job, config=config)
        assert res.preemption_executed is False
        assert res.status == STATUS_DENIED
        assert res.requires_human_approval is True
        assert "Cannot establish interruptibility or safety" in res.decision_reason
        assert "escalate for manual supervisor review" in res.recommended_action

    def test_scenario_5_allow_unknown_interruptibility_when_configured(self) -> None:
        """Scenario 5: Config allows unknown interruptibility when explicitly permitted."""
        config = PreemptionConfig(allow_unknown_interruptibility=True)

        current_job = MaintenanceJob(
            job_id="JOB-CUSTOM",
            machine_id="M-01",
            priority_score=15.0,
            job_type="custom_unclassified_procedure",
            is_interruptible=None,
        )
        incoming_job = MaintenanceJob(
            job_id="JOB-URGENT",
            machine_id="M-02",
            priority_score=90.0,
        )

        res = evaluate_preemption(current_job, incoming_job, config=config)
        assert res.preemption_executed is True
        assert res.status == STATUS_EXECUTED

    def test_non_interruptible_job_state(self) -> None:
        """A completed or canceled job cannot be interrupted."""
        current_job = MaintenanceJob(
            job_id="JOB-DONE",
            machine_id="M-01",
            priority_score=10.0,
            status=JOB_STATUS_COMPLETED,
            is_interruptible=True,
        )
        incoming_job = MaintenanceJob(
            job_id="JOB-URGENT",
            machine_id="M-02",
            priority_score=90.0,
        )
        res = evaluate_preemption(current_job, incoming_job)
        assert res.preemption_executed is False
        assert res.status == STATUS_DENIED
        assert "cannot be interrupted" in res.decision_reason


class TestHumanApprovalAndGovernance:
    """Tests evaluating supervisor sign-off requirements and Maintenance Policy Guardrails integration."""

    def test_scenario_6_human_approval_required_but_not_granted_pending_approval(self) -> None:
        """Scenario 6: Human approval is required but not yet granted."""
        config = PreemptionConfig(require_human_approval=True)

        current_job = MaintenanceJob(
            job_id="JOB-ACTIVE",
            machine_id="M-01",
            priority_score=20.0,
            status=JOB_STATUS_IN_PROGRESS,
            is_interruptible=True,
        )
        incoming_job = MaintenanceJob(
            job_id="JOB-URGENT",
            machine_id="M-02",
            priority_score=85.0,
        )

        # 1. Non-mutating evaluation returns pending_approval
        res = evaluate_preemption(current_job, incoming_job, config=config, approved=False)
        assert res.preemption_considered is True
        assert res.preemption_executed is False
        assert res.requires_human_approval is True
        assert res.status == STATUS_PENDING_APPROVAL
        assert "human supervisor approval is required" in res.decision_reason
        assert "Await supervisor sign-off" in res.recommended_action
        assert res.interrupted_job_status == JOB_STATUS_IN_PROGRESS

        # 2. Execution attempt without approval does NOT mutate state
        exec_res, paused_job, new_job = execute_preemption(
            current_job, incoming_job, config=config, approved=False
        )
        assert exec_res.preemption_executed is False
        assert paused_job.status == JOB_STATUS_IN_PROGRESS  # Current job stays active
        assert new_job.status != JOB_STATUS_IN_PROGRESS     # Incoming job not dispatched

    def test_scenario_7_human_approval_granted_executes_preemption(self) -> None:
        """Scenario 7: Human approval is granted and preemption executes."""
        config = PreemptionConfig(require_human_approval=True)

        current_job = MaintenanceJob(
            job_id="JOB-ACTIVE",
            machine_id="M-01",
            priority_score=20.0,
            is_interruptible=True,
            technician_id="TECH-02",
        )
        incoming_job = MaintenanceJob(
            job_id="JOB-URGENT",
            machine_id="M-02",
            priority_score=85.0,
        )

        # Approved by supervisor
        res, paused_job, new_job = execute_preemption(
            current_job, incoming_job, config=config, approved=True, timestamp="2026-10-22T13:00:00Z"
        )
        assert res.preemption_executed is True
        assert res.status == STATUS_EXECUTED
        assert res.requires_human_approval is False
        assert paused_job.status == JOB_STATUS_INTERRUPTED
        assert paused_job.interrupted_at == "2026-10-22T13:00:00Z"
        assert new_job.status == JOB_STATUS_IN_PROGRESS
        assert new_job.technician_id == "TECH-02"

    def test_scenario_12_guardrail_mandatory_review_blocks_unauthorized_execution(self) -> None:
        """Scenario 12: Guardrails require mandatory review for critical risk machines."""
        guardrail_cfg = MaintenancePolicyConfig(
            risk_config=RiskTierConfig(critical_threshold=0.85),
            mandatory_review_critical=True,
        )
        # require_human_approval is False globally, but Guardrail requires review for p >= 0.85
        config = PreemptionConfig(require_human_approval=False, guardrail_config=guardrail_cfg)

        current_job = MaintenanceJob(
            job_id="JOB-ACTIVE",
            machine_id="M-01",
            priority_score=20.0,
            is_interruptible=True,
        )
        # Critical incoming machine with failure_probability = 0.92 >= 0.85
        critical_incoming = MaintenanceJob(
            job_id="JOB-CRIT-99",
            machine_id="M-CRIT",
            priority_score=92.0,
            failure_probability=0.92,
            alert_category=ALERT_CATEGORY_PREDICTED_HIGH_RISK,
        )

        # Guardrail triggers pending_approval because approved=False
        res = evaluate_preemption(current_job, critical_incoming, config=config, approved=False)
        assert res.preemption_executed is False
        assert res.requires_human_approval is True
        assert res.status == STATUS_PENDING_APPROVAL

        # When supervisor approves, it executes
        res_approved = evaluate_preemption(current_job, critical_incoming, config=config, approved=True)
        assert res_approved.preemption_executed is True
        assert res_approved.status == STATUS_EXECUTED


class TestWorkPreservationAndRescheduling:
    """Tests verifying work preservation, metadata integrity, and rescheduling queues."""

    def test_scenario_8_single_active_job_invariant_and_capacity_preserved(self) -> None:
        """Scenario 8: Technician capacity and single-active-job invariant are strictly preserved."""
        manager = PreemptionManager()
        manager.register_technician("TECH-01")

        job_c = MaintenanceJob(
            job_id="JOB-C",
            machine_id="CNC-03",
            priority_score=18.0,
            is_interruptible=True,
        )
        manager.assign_job("TECH-01", job_c)

        # Single active job currently assigned
        assert len(manager.get_active_jobs()) == 1
        assert manager.get_active_jobs()["TECH-01"].job_id == "JOB-C"

        # Direct assignment of a second job while first is active raises ValueError
        job_x = MaintenanceJob(job_id="JOB-X", machine_id="CNC-09", priority_score=20.0)
        with pytest.raises(ValueError, match="already actively working"):
            manager.assign_job("TECH-01", job_x)

        # Preemption transfers the technician
        job_a = MaintenanceJob(
            job_id="JOB-A",
            machine_id="PRESS-01",
            priority_score=95.0,
            alert_category=ALERT_CATEGORY_ACTUAL_FAILURE,
        )
        res = manager.handle_incoming_alert(job_a, technician_id="TECH-01")
        assert res.preemption_executed is True

        # Invariant maintained: exactly 1 active job for TECH-01
        active_jobs = manager.get_active_jobs()
        assert len(active_jobs) == 1
        assert active_jobs["TECH-01"].job_id == "JOB-A"
        assert active_jobs["TECH-01"].status == JOB_STATUS_IN_PROGRESS

        # Capacity did not increase
        techs = manager.get_technicians()
        assert techs["TECH-01"].active_job_id == "JOB-A"
        assert "JOB-C" in techs["TECH-01"].interrupted_jobs

    def test_scenario_9_interrupted_job_progress_and_metadata_preserved_in_reschedule_queue(self) -> None:
        """Scenario 9: Interrupted job progress/state is preserved for later rescheduling."""
        manager = PreemptionManager()
        job_1 = MaintenanceJob(
            job_id="JOB-INSP",
            machine_id="LATHE-02",
            priority_score=25.0,
            job_type="routine_inspection",
            is_interruptible=True,
            progress={"completed_steps": 3, "total_steps": 5, "percent": 60.0},
            started_at="2026-10-22T08:00:00Z",
            metadata={"assigned_bay": "Bay-4", "tool_kit": "TK-88"},
        )
        manager.assign_job("TECH-01", job_1)

        job_urgent = MaintenanceJob(
            job_id="JOB-URGENT",
            machine_id="PRESS-05",
            priority_score=92.0,
            alert_category=ALERT_CATEGORY_ACTUAL_FAILURE,
        )

        res = manager.handle_incoming_alert(job_urgent, timestamp="2026-10-22T09:45:00Z")
        assert res.preemption_executed is True

        # Check reschedule queue
        queue = manager.get_reschedule_queue()
        assert len(queue) == 1
        interrupted = queue[0]

        # Verify all metadata preserved and never discarded or marked completed
        assert interrupted.job_id == "JOB-INSP"
        assert interrupted.status == JOB_STATUS_INTERRUPTED
        assert interrupted.status != JOB_STATUS_COMPLETED
        assert interrupted.progress == {"completed_steps": 3, "total_steps": 5, "percent": 60.0}
        assert interrupted.started_at == "2026-10-22T08:00:00Z"
        assert interrupted.interrupted_at == "2026-10-22T09:45:00Z"
        assert interrupted.preempted_by_job_id == "JOB-URGENT"
        assert interrupted.metadata["tool_kit"] == "TK-88"
        assert "Actual machine breakdown failure" in str(interrupted.interruption_reason)

    def test_timestamp_not_fabricated_when_not_provided(self) -> None:
        """Engine does not invent timestamps or progress when caller omits them."""
        job_cur = MaintenanceJob(
            job_id="JOB-1",
            machine_id="M-01",
            priority_score=20.0,
            is_interruptible=True,
            progress=None,
            started_at=None,
        )
        job_inc = MaintenanceJob(
            job_id="JOB-2",
            machine_id="M-02",
            priority_score=80.0,
        )

        _, paused_job, _ = execute_preemption(job_cur, job_inc, timestamp=None)
        assert paused_job.interrupted_at is None
        assert paused_job.progress is None


class TestTechnicianFleetAndInvariants:
    """Tests managing multiple technicians, candidate selection, and edge cases."""

    def test_scenario_10_unrelated_technician_assignments_remain_unchanged(self) -> None:
        """Scenario 10: Existing assignments for other technicians remain unchanged."""
        manager = PreemptionManager()
        job_1 = MaintenanceJob(job_id="JOB-1", machine_id="M-01", priority_score=15.0, is_interruptible=True)
        job_2 = MaintenanceJob(job_id="JOB-2", machine_id="M-02", priority_score=35.0, is_interruptible=True)

        manager.assign_job("TECH-01", job_1)
        manager.assign_job("TECH-02", job_2)

        # Incoming job targets TECH-01
        job_urgent = MaintenanceJob(job_id="JOB-URGENT", machine_id="M-99", priority_score=85.0)
        res = manager.handle_incoming_alert(job_urgent, technician_id="TECH-01")
        assert res.preemption_executed is True

        active = manager.get_active_jobs()
        # TECH-01 is reassigned
        assert active["TECH-01"].job_id == "JOB-URGENT"
        # TECH-02 is strictly preserved and untouched
        assert active["TECH-02"].job_id == "JOB-2"
        assert active["TECH-02"].status == JOB_STATUS_IN_PROGRESS

    def test_scenario_11_duplicate_and_repeated_preemption_attempts_handled_safely(self) -> None:
        """Scenario 11: Duplicate or repeated preemption attempts are handled safely."""
        current_job = MaintenanceJob(
            job_id="JOB-1",
            machine_id="M-01",
            priority_score=20.0,
            status=JOB_STATUS_IN_PROGRESS,
            is_interruptible=True,
        )

        # 1. Attempting to preempt with the same job ID is rejected
        res_self = evaluate_preemption(current_job, current_job)
        assert res_self.preemption_executed is False
        assert res_self.status == STATUS_DENIED
        assert "refer to the same job identifier" in res_self.decision_reason

        # 2. Attempting to preempt an already interrupted job is rejected
        current_job.status = JOB_STATUS_INTERRUPTED
        incoming_job = MaintenanceJob(job_id="JOB-2", machine_id="M-02", priority_score=80.0)
        res_dup = evaluate_preemption(current_job, incoming_job)
        assert res_dup.preemption_executed is False
        assert res_dup.status == STATUS_DENIED
        assert "already interrupted" in res_dup.decision_reason

        # 3. Attempting to assign an already active job is rejected
        current_job.status = JOB_STATUS_IN_PROGRESS
        incoming_job.status = JOB_STATUS_IN_PROGRESS
        res_act = evaluate_preemption(current_job, incoming_job)
        assert res_act.preemption_executed is False
        assert res_act.status == STATUS_DENIED
        assert "already in status 'in_progress'" in res_act.decision_reason

    def test_idle_technician_assigned_directly_without_preemption(self) -> None:
        """If a technician is idle, direct assignment occurs without preemption."""
        manager = PreemptionManager()
        manager.register_technician("TECH-IDLE")

        job = MaintenanceJob(job_id="JOB-NEW", machine_id="M-01", priority_score=40.0)
        res = manager.handle_incoming_alert(job, technician_id="TECH-IDLE")

        assert res.preemption_considered is False
        assert res.preemption_executed is False
        assert res.status == STATUS_NO_PREEMPTION
        assert "assigned directly without preemption" in res.decision_reason
        assert manager.get_active_jobs()["TECH-IDLE"].job_id == "JOB-NEW"

    def test_manager_deterministic_tie_breaking_for_candidate_selection(self) -> None:
        """When technician_id is not specified, best preemption candidate is chosen deterministically."""
        manager = PreemptionManager()
        # Tech 2 has lower priority (15.0) than Tech 1 (30.0)
        job_t1 = MaintenanceJob(job_id="JOB-1", machine_id="M-01", priority_score=30.0, is_interruptible=True)
        job_t2 = MaintenanceJob(job_id="JOB-2", machine_id="M-02", priority_score=15.0, is_interruptible=True)

        manager.assign_job("TECH-01", job_t1)
        manager.assign_job("TECH-02", job_t2)

        # Incoming job with score 70.0
        # Preempting TECH-02 gives delta 55.0, preempting TECH-01 gives delta 40.0
        # TECH-02 should be selected because it yields the highest delta (lowest priority job interrupted)
        incoming = MaintenanceJob(job_id="JOB-INC", machine_id="M-99", priority_score=70.0)
        res = manager.handle_incoming_alert(incoming)

        assert res.preemption_executed is True
        assert res.technician_id == "TECH-02"
        assert res.interrupted_job_id == "JOB-2"
        assert manager.get_active_jobs()["TECH-01"].job_id == "JOB-1"
        assert manager.get_active_jobs()["TECH-02"].job_id == "JOB-INC"


class TestValidationAndDeterministicDecisions:
    """Tests verifying input validation, error handling, and deterministic explain/to_dict outputs."""

    def test_scenario_14_invalid_preemption_config_rejected(self) -> None:
        """Scenario 14: Invalid configuration parameters raise appropriate errors."""
        with pytest.raises(TypeError, match="enabled must be a boolean"):
            PreemptionConfig(enabled="yes")  # type: ignore

        with pytest.raises(TypeError, match="min_priority_delta must be numeric"):
            PreemptionConfig(min_priority_delta="ten")  # type: ignore

        with pytest.raises(ValueError, match="min_priority_delta must be non-negative"):
            PreemptionConfig(min_priority_delta=-5.0)

        with pytest.raises(ValueError, match="min_priority_delta must be finite"):
            PreemptionConfig(min_priority_delta=float("inf"))

        with pytest.raises(TypeError, match="require_human_approval must be a boolean"):
            PreemptionConfig(require_human_approval=1)  # type: ignore

    def test_scenario_14_invalid_job_attributes_rejected(self) -> None:
        """Scenario 14: Invalid job scores or probabilities raise errors."""
        with pytest.raises(TypeError, match="priority_score must be numeric"):
            MaintenanceJob(job_id="J1", machine_id="M1", priority_score="invalid")

        with pytest.raises(ValueError, match="priority_score must be finite"):
            MaintenanceJob(job_id="J1", machine_id="M1", priority_score=float("nan"))

        with pytest.raises(ValueError, match="failure_probability must be in"):
            MaintenanceJob(job_id="J1", machine_id="M1", priority_score=10.0, failure_probability=1.5)

    def test_scenario_14_deterministic_explain_and_to_dict(self) -> None:
        """Scenario 14: Structured result serialization and explain methods work accurately."""
        cur = MaintenanceJob(job_id="J-1", machine_id="M-1", priority_score=10.0, is_interruptible=True)
        inc = MaintenanceJob(job_id="J-2", machine_id="M-2", priority_score=80.0)

        res = evaluate_preemption(cur, inc, technician_id="TECH-01")
        d = res.to_dict()
        assert d["preemption_executed"] is True
        assert d["technician_id"] == "TECH-01"
        assert d["status"] == STATUS_EXECUTED
        assert d["interrupted_job"]["job_id"] == "J-1"
        assert d["incoming_job"]["job_id"] == "J-2"

        # Item access
        assert res["status"] == STATUS_EXECUTED
        assert res["technician_id"] == "TECH-01"

        # Explain string
        explanation = res.explain()
        assert "EXECUTED" in explanation
        assert "TECH-01" in explanation
        assert "Priority: 80.0" in explanation

        # Manager explain and to_dict
        manager = PreemptionManager()
        manager.register_technician("TECH-01")
        manager.assign_job("TECH-01", cur)
        manager.handle_incoming_alert(inc)
        mgr_dict = manager.to_dict()
        assert "TECH-01" in mgr_dict["technicians"]
        assert len(mgr_dict["reschedule_queue"]) == 1
        mgr_exp = manager.explain()
        assert "ForgeGuard Person 2 -- Preemption Manager Status" in mgr_exp
        assert "TECH-01 -> Job J-2" in mgr_exp


class TestEngineIntegration:
    """Tests evaluating integration with ScheduleResult and PipelineResult."""

    def test_scenario_15_schedule_result_evaluate_preemption_integration(self) -> None:
        """Scenario 15: Chaining evaluate_preemption from ScheduleResult."""
        fleet_df = pd.DataFrame({
            "machine_id": ["CNC-01", "CNC-02", "CNC-03"],
        })
        probs = [0.85, 0.40, 0.10]
        schedule = plan_shift(fleet_df, probabilities=probs, slots=1, threshold=0.50)
        assert schedule.selected_machines == ["CNC-01"]

        # Urgent incoming job with higher priority
        incoming_job = MaintenanceJob(
            job_id="JOB-EMERGENCY",
            machine_id="PRESS-99",
            priority_score=95.0,
            alert_category=ALERT_CATEGORY_ACTUAL_FAILURE,
        )

        res = schedule.evaluate_preemption(incoming_job, technician_id="TECH-01")
        assert res.preemption_considered is True
        assert res.preemption_executed is True
        assert res.interrupted_job_id == "JOB-CNC-01"
        assert res.current_priority_score == pytest.approx(17.0)  # 0.85 * 20.0 = 17.0
        assert res.incoming_priority_score == 95.0

    def test_scenario_15_schedule_result_empty_assignments_handled_safely(self) -> None:
        """Scenario 15: ScheduleResult with 0 slots or no alerts handles preemption evaluation cleanly."""
        fleet_df = pd.DataFrame({
            "machine_id": ["CNC-01", "CNC-02"],
        })
        probs = [0.20, 0.10]
        # Threshold 0.50 means 0 alerts triggered
        schedule = plan_shift(fleet_df, probabilities=probs, slots=2, threshold=0.50)
        assert len(schedule.selected_machines) == 0

        incoming_job = MaintenanceJob(job_id="JOB-1", machine_id="M-01", priority_score=80.0)
        res = schedule.evaluate_preemption(incoming_job)
        assert res.preemption_considered is False
        assert res.preemption_executed is False
        assert res.status == STATUS_NO_PREEMPTION
        assert "No active machine assignments exist" in res.decision_reason

    def test_scenario_15_pipeline_result_evaluate_preemption_integration(self) -> None:
        """Scenario 15: Chaining evaluate_preemption from PipelineResult."""
        from engine.pipeline import integrate_predictions

        fleet_df = pd.DataFrame({
            "machine_id": ["M-101", "M-102"],
            "failure_probability": [0.90, 0.20],
            "predicted_failure_mode": ["Heat Dissipation", "No Failure"],
        })
        pipe_res = integrate_predictions(
            predictions_df=fleet_df,
            slots=1,
            threshold=0.50,
        )
        assert pipe_res.selected_machines == ["M-101"]

        incoming_urgent = MaintenanceJob(
            job_id="JOB-SUDDEN-FAIL",
            machine_id="M-999",
            priority_score=98.0,
            alert_category=ALERT_CATEGORY_ACTUAL_FAILURE,
        )

        res = pipe_res.evaluate_preemption(incoming_urgent)
        assert res.preemption_executed is True
        assert res.interrupted_job_id == "JOB-M-101"
        assert res.incoming_job_id == "JOB-SUDDEN-FAIL"
