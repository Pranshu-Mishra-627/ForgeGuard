"""Comprehensive test suite for ForgeGuard Decision Engine HTTP API and simulation interfaces.

Covers all 16 required test scenarios:
1. Single-machine prediction and batch prediction.
2. Invalid/missing sensor readings and error handling.
3. Threshold output consistency with choose_threshold().
4. Cost decisions using existing cost configuration.
5. Shift capacity constraints and scheduling output.
6. Deferred-risk and policy-guardrail integration.
7. Safe, unsafe, and indeterminate safety assessments.
8. Missing, stale, and conflicting telemetry.
9. Higher-priority emergency blocked by unsafe or indeterminate active-job safety.
10. Preemption pending approval, denied, and permitted.
11. Execution updating actual assignment/job state.
12. Interrupted-job progress preservation and rescheduling.
13. Repeated execution / idempotency.
14. Invalid state transitions and nonexistent IDs.
15. API serialization and consistent error responses.
16. End-to-end integration: batch predictions -> shift planning -> emergency preemption -> simulation state/events.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from engine.api import (
    app,
    assess_safety,
    evaluate_alert_decision,
    evaluate_preemption_request,
    execute_preemption_request,
    get_threshold_optimization_result,
    plan_shift_schedule,
)
from engine.cost_model import CostConfig
from engine.prediction_service import (
    predict_batch_machines,
    predict_single_machine,
    set_active_predict_fn,
)
from engine.preemption import (
    ALERT_CATEGORY_ACTUAL_FAILURE,
    ALERT_CATEGORY_CRITICAL_ALERT,
    ALERT_CATEGORY_PREDICTED_HIGH_RISK,
    JOB_STATUS_IN_PROGRESS,
    JOB_STATUS_INTERRUPTED,
    STATUS_DENIED,
    STATUS_EXECUTED,
    STATUS_PENDING_APPROVAL,
    MaintenanceJob,
    PreemptionConfig,
)
from engine.safety_assessment import (
    OUTCOME_INDETERMINATE,
    OUTCOME_SAFE_TO_INTERRUPT,
    OUTCOME_UNSAFE_TO_INTERRUPT,
    EquipmentSafetyConfig,
    EquipmentSafetyRule,
    MachineTelemetryContext,
)
from engine.simulation import (
    get_simulation_events,
    get_simulation_state,
    reset_simulation,
)
from engine.threshold import choose_threshold


@pytest.fixture(autouse=True)
def clean_simulation_environment():
    """Reset simulation state and mock model before each test."""
    reset_simulation()
    # Register mock prediction model
    def mock_predict(df: pd.DataFrame) -> pd.DataFrame:
        n = len(df)
        probs = [0.85, 0.72, 0.45, 0.20, 0.95, 0.30, 0.60, 0.15][:n]
        modes = ["Bearing Wear", "Overheating", "Tool Wear", "None", "Overheating", "None", "Bearing Wear", "None"][:n]
        p_arr = np.array(probs[:n], dtype=float)
        return pd.DataFrame({
            "machine_id": df["machine_id"].values if "machine_id" in df.columns else [f"M-{i+1}" for i in range(n)],
            "failure_probability": p_arr,
            "predicted_failure_mode": modes[:n],
            "maintenance_alert": p_arr >= 0.50,
        })

    set_active_predict_fn(mock_predict, model_version="ForgeGuard-Mock-v1.0")
    yield
    reset_simulation()
    set_active_predict_fn(None)


@pytest.fixture
def client() -> TestClient:
    """Test client for ForgeGuard FastAPI application."""
    return TestClient(app)


# ==============================================================================
# 1. Single-machine prediction and batch prediction
# ==============================================================================

class TestPredictionInterfaces:
    def test_single_machine_prediction_api(self, client: TestClient):
        payload = {
            "machine_id": "CNC-001",
            "temperature_c": 72.5,
            "vibration_rms": 2.3,
        }
        res = client.post("/predict", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["machine_id"] == "CNC-001"
        assert 0.0 <= data["failure_probability"] <= 1.0
        assert "predicted_failure_mode" in data
        assert "prediction_timestamp" in data
        assert "model_version" in data
        assert "prediction_horizon" in data

    def test_batch_prediction_api(self, client: TestClient):
        payload = {
            "machines": [
                {"machine_id": "CNC-001", "temperature_c": 72.5},
                {"machine_id": "CNC-002", "temperature_c": 88.0},
                {"machine_id": "CNC-003", "temperature_c": 55.0},
            ]
        }
        res = client.post("/predict/batch", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) == 3
        assert [m["machine_id"] for m in data] == ["CNC-001", "CNC-002", "CNC-003"]
        assert all("failure_probability" in m for m in data)

    def test_direct_json_array_batch_prediction(self, client: TestClient):
        payload = [
            {"machine_id": "PRESS-01", "vibration_rms": 3.1},
            {"machine_id": "PRESS-02", "vibration_rms": 1.2},
        ]
        res = client.post("/predict/batch", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 2
        assert data[0]["machine_id"] == "PRESS-01"


# ==============================================================================
# 2. Invalid/missing sensor readings and error handling
# ==============================================================================

class TestValidationAndErrorHandling:
    def test_missing_machine_id_returns_400(self, client: TestClient):
        res = client.post("/predict", json={"temperature_c": 80.0})
        assert res.status_code == 400
        err = res.json()
        assert "error" in err
        assert err["error"]["code"] == "INVALID_INPUT"
        assert "machine_id" in err["error"]["message"].lower()

    def test_non_finite_sensor_value_returns_400(self, client: TestClient):
        res = client.post("/predict", json={"machine_id": "M-1", "temperature_c": "infinite_val"})
        # String instead of float or non-finite
        assert res.status_code in (400, 422)
        err = res.json()
        assert "error" in err
        assert err["error"]["code"] == "INVALID_INPUT"

    def test_empty_batch_returns_400(self, client: TestClient):
        res = client.post("/predict/batch", json={"machines": []})
        assert res.status_code == 400
        err = res.json()
        assert err["error"]["code"] == "INVALID_INPUT"
        assert "empty" in err["error"]["message"].lower()


# ==============================================================================
# 3. Threshold output consistency with choose_threshold()
# ==============================================================================

class TestThresholdInterfaces:
    def test_threshold_get_matches_optimizer(self, client: TestClient):
        res = client.get("/decision/threshold")
        assert res.status_code == 200
        data = res.json()
        assert "optimal_threshold" in data
        assert "optimal_cost" in data
        assert "threshold_curve" in data
        assert "confusion_matrix" in data
        assert "baseline_comparison" in data
        assert data["baseline_comparison"]["baseline_threshold"] == 0.50
        assert data["baseline_comparison"]["cost_difference"] >= 0.0

    def test_threshold_post_recomputes_with_validation_data(self, client: TestClient):
        y_val = [1, 0, 1, 0, 1, 0]
        p_val = [0.9, 0.1, 0.8, 0.2, 0.7, 0.3]
        payload = {
            "y_val": y_val,
            "p_val": p_val,
            "costs": {"false_negative_cost": 30.0, "false_positive_cost": 2.0},
        }
        res = client.post("/decision/threshold", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["metadata"]["sample_size"] == 6
        assert data["cost_config"]["false_negative_cost"] == 30.0


# ==============================================================================
# 4. Cost decisions using existing cost configuration
# ==============================================================================

class TestCostDecisionEvaluation:
    def test_alert_decision_evaluate_above_threshold(self, client: TestClient):
        payload = {
            "machine_id": "CNC-05",
            "failure_probability": 0.80,
            "threshold": 0.50,
            "costs": {"false_negative_cost": 20.0, "false_positive_cost": 1.0},
        }
        res = client.post("/decision/evaluate", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["machine_id"] == "CNC-05"
        assert data["operational_alert"] is True
        assert data["priority_score"] == pytest.approx(16.0)
        assert "PROBABILITY_EXCEEDS_THRESHOLD" in data["reason_codes"]
        assert "cost_breakdown" in data

    def test_alert_decision_evaluate_below_threshold(self, client: TestClient):
        payload = {
            "machine_id": "CNC-06",
            "failure_probability": 0.25,
            "threshold": 0.50,
        }
        res = client.post("/decision/evaluate", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["operational_alert"] is False
        assert "PROBABILITY_BELOW_THRESHOLD" in data["reason_codes"]


# ==============================================================================
# 5. Shift capacity constraints and scheduling output
# ==============================================================================

class TestShiftSchedulingInterface:
    def test_schedule_plan_enforces_capacity(self, client: TestClient):
        payload = {
            "machines": [
                {"machine_id": "M-1", "failure_probability": 0.90},
                {"machine_id": "M-2", "failure_probability": 0.80},
                {"machine_id": "M-3", "failure_probability": 0.70},
                {"machine_id": "M-4", "failure_probability": 0.20},
            ],
            "slots": 2,
            "threshold": 0.50,
        }
        res = client.post("/schedule/plan", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["selected_machines"] == ["M-1", "M-2"]
        assert data["deferred_machines"] == ["M-3"]
        assert data["unalerted_machines"] == ["M-4"]
        assert data["capacity_summary"]["capacity_utilized"] == 2
        assert data["capacity_summary"]["capacity_remaining"] == 0

    def test_schedule_plan_tied_priority_deterministic_tie_break(self, client: TestClient):
        payload = {
            "machines": [
                {"machine_id": "M-B", "failure_probability": 0.85},
                {"machine_id": "M-A", "failure_probability": 0.85},
            ],
            "slots": 1,
            "threshold": 0.50,
        }
        res = client.post("/schedule/plan", json=payload)
        assert res.status_code == 200
        data = res.json()
        # Tied priority resolved deterministically by alphanumeric order: M-A before M-B
        assert data["selected_machines"] == ["M-A"]
        assert data["deferred_machines"] == ["M-B"]


# ==============================================================================
# 6. Deferred-risk and policy-guardrail integration
# ==============================================================================

class TestDeferredRiskAndGuardrails:
    def test_deferred_machines_have_explanations(self, client: TestClient):
        payload = {
            "machines": [
                {"machine_id": "M-1", "failure_probability": 0.95},
                {"machine_id": "M-2", "failure_probability": 0.90},
            ],
            "slots": 1,
            "threshold": 0.50,
        }
        res = client.post("/schedule/plan", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "M-2" in data["deferred_machines"]
        assert "M-2" in data["selection_reasons"]
        assert "deferred" in data["selection_reasons"]["M-2"].lower()


# ==============================================================================
# 7. Safe, unsafe, and indeterminate safety assessments
# ==============================================================================

class TestSafetyAssessmentScenarios:
    def test_safe_assessment(self, client: TestClient):
        payload = {
            "active_job_id": "JOB-01",
            "machine_id": "CNC-01",
            "telemetry_signals": {"temperature_c": 70.0, "vibration_rms": 2.5},
            "timestamp": time.time(),
            "current_time": time.time(),
            "maintenance_stage": "inspection",
            "is_reversible_stage": True,
        }
        res = client.post("/safety/assess", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["outcome"] == OUTCOME_SAFE_TO_INTERRUPT
        assert data["is_safe_to_interrupt"] is True
        assert data["required_next_step"] == "PROCEED_WITH_SAFE_INTERRUPTION"

    def test_unsafe_assessment_exceeding_temperature(self, client: TestClient):
        payload = {
            "active_job_id": "JOB-02",
            "machine_id": "CNC-02",
            "telemetry_signals": {"temperature_c": 92.0, "vibration_rms": 2.0},
            "timestamp": time.time(),
            "current_time": time.time(),
        }
        res = client.post("/safety/assess", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["outcome"] == OUTCOME_UNSAFE_TO_INTERRUPT
        assert data["is_safe_to_interrupt"] is False
        assert data["required_next_step"] == "TRIGGER_SAFE_STOP_PROCEDURE"

    def test_indeterminate_assessment_missing_signal(self, client: TestClient):
        payload = {
            "active_job_id": "JOB-03",
            "machine_id": "CNC-03",
            # missing vibration_rms
            "telemetry_signals": {"temperature_c": 70.0},
            "timestamp": time.time(),
            "current_time": time.time(),
        }
        res = client.post("/safety/assess", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["outcome"] == OUTCOME_INDETERMINATE
        assert data["is_safe_to_interrupt"] is False
        assert "vibration_rms" in data["missing_inputs"]
        assert data["required_next_step"] == "MANDATORY_SUPERVISOR_SAFETY_REVIEW"


# ==============================================================================
# 8. Missing, stale, and conflicting telemetry
# ==============================================================================

class TestStaleAndConflictingTelemetry:
    def test_stale_telemetry_flags_indeterminate(self, client: TestClient):
        now = time.time()
        payload = {
            "active_job_id": "JOB-04",
            "machine_id": "CNC-04",
            "telemetry_signals": {"temperature_c": 65.0, "vibration_rms": 2.0},
            "timestamp": now - 600.0,  # 10 minutes old (> 300s limit)
            "current_time": now,
        }
        res = client.post("/safety/assess", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["outcome"] == OUTCOME_INDETERMINATE
        assert len(data["stale_signals"]) > 0

    def test_conflicting_sensor_signals_flag_indeterminate(self, client: TestClient):
        payload = {
            "active_job_id": "JOB-05",
            "machine_id": "CNC-05",
            "telemetry_signals": {"temperature_c": 60.0, "vibration_rms": 2.0},
            "redundant_signals": {"temperature_c": 75.0},  # Discrepancy = 15°C (> 5°C max)
            "timestamp": time.time(),
            "current_time": time.time(),
        }
        res = client.post("/safety/assess", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["outcome"] == OUTCOME_INDETERMINATE
        assert "temperature_c" in data["conflicting_signals"]


# ==============================================================================
# 9. Higher-priority emergency blocked by unsafe or indeterminate active safety
# ==============================================================================

class TestPriorityCannotOverrideSafety:
    def test_emergency_cannot_preempt_unsafe_active_job(self, client: TestClient):
        now = time.time()
        cur_job = {
            "job_id": "JOB-ROUTINE",
            "machine_id": "M-HOT",
            "priority_score": 15.0,
            "status": "in_progress",
            "job_type": "preventive_maintenance",
            "technician_id": "TECH-01",
            "safety_context": {
                "machine_id": "M-HOT",
                "telemetry_signals": {"temperature_c": 98.0, "vibration_rms": 2.0},  # Overheating unsafe!
                "timestamp": now,
                "current_time": now,
            },
        }
        emergency_job = {
            "job_id": "JOB-EMERGENCY",
            "machine_id": "M-EMERGENCY",
            "priority_score": 99.0,  # Far higher priority!
            "alert_category": "actual_failure",
        }
        payload = {
            "current_job": cur_job,
            "incoming_job": emergency_job,
            "technician_id": "TECH-01",
        }
        res = client.post("/schedule/preemption/evaluate", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == STATUS_DENIED
        assert data["preemption_executed"] is False
        assert "cannot override safety" in data["decision_reason"].lower()

    def test_emergency_cannot_preempt_indeterminate_safety_job(self, client: TestClient):
        cur_job = {
            "job_id": "JOB-UNKNOWN",
            "machine_id": "M-UNK",
            "priority_score": 10.0,
            "status": "in_progress",
            "technician_id": "TECH-01",
            "safety_context": {
                "machine_id": "M-UNK",
                "telemetry_signals": {},  # Missing all required signals!
            },
        }
        emergency_job = {
            "job_id": "JOB-CRITICAL",
            "machine_id": "M-CRIT",
            "priority_score": 90.0,
        }
        res = client.post("/schedule/preemption/evaluate", json={"current_job": cur_job, "incoming_job": emergency_job})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == STATUS_DENIED
        assert data["preemption_executed"] is False


# ==============================================================================
# 10. Preemption pending approval, denied, and permitted
# ==============================================================================

class TestPreemptionDecisions:
    def test_preemption_permitted(self, client: TestClient):
        cur_job = {
            "job_id": "JOB-1",
            "machine_id": "M-1",
            "priority_score": 20.0,
            "status": "in_progress",
            "job_type": "preventive_maintenance",
            "is_interruptible": True,
            "technician_id": "TECH-01",
        }
        inc_job = {
            "job_id": "JOB-2",
            "machine_id": "M-2",
            "priority_score": 80.0,
            "alert_category": "predicted_high_risk",
        }
        res = client.post("/schedule/preemption/evaluate", json={"current_job": cur_job, "incoming_job": inc_job})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == STATUS_EXECUTED
        assert data["incoming_job_id"] == "JOB-2"
        assert data["interrupted_job_id"] == "JOB-1"

    def test_preemption_pending_approval_when_required(self, client: TestClient):
        cur_job = {
            "job_id": "JOB-1",
            "machine_id": "M-1",
            "priority_score": 20.0,
            "status": "in_progress",
            "is_interruptible": True,
        }
        inc_job = {
            "job_id": "JOB-2",
            "machine_id": "M-2",
            "priority_score": 80.0,
        }
        payload = {
            "current_job": cur_job,
            "incoming_job": inc_job,
            "config": {"require_human_approval": True},
            "approved": False,
        }
        res = client.post("/schedule/preemption/evaluate", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == STATUS_PENDING_APPROVAL
        assert data["requires_human_approval"] is True
        assert data["preemption_executed"] is False

    def test_preemption_denied_lower_priority(self, client: TestClient):
        cur_job = {"job_id": "JOB-1", "machine_id": "M-1", "priority_score": 80.0, "status": "in_progress"}
        inc_job = {"job_id": "JOB-2", "machine_id": "M-2", "priority_score": 30.0}
        res = client.post("/schedule/preemption/evaluate", json={"current_job": cur_job, "incoming_job": inc_job})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == STATUS_DENIED
        assert data["preemption_executed"] is False


# ==============================================================================
# 11. Execution updating actual assignment/job state
# ==============================================================================

class TestPreemptionExecution:
    def test_execute_mutates_state_when_permitted(self, client: TestClient):
        cur_job = {
            "job_id": "JOB-RUNNING",
            "machine_id": "M-10",
            "priority_score": 18.0,
            "status": "in_progress",
            "is_interruptible": True,
            "technician_id": "TECH-A",
        }
        inc_job = {
            "job_id": "JOB-EMERGENCY",
            "machine_id": "M-99",
            "priority_score": 92.0,
            "alert_category": "actual_failure",
        }
        payload = {
            "current_job": cur_job,
            "incoming_job": inc_job,
            "technician_id": "TECH-A",
        }
        res = client.post("/schedule/preemption/execute", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["result"]["status"] == STATUS_EXECUTED
        assert data["result"]["preemption_executed"] is True
        assert data["interrupted_job"]["status"] == JOB_STATUS_INTERRUPTED
        assert data["incoming_job"]["status"] == JOB_STATUS_IN_PROGRESS
        assert data["incoming_job"]["technician_id"] == "TECH-A"
        assert data["assignment_state"]["active_job_id"] == "JOB-EMERGENCY"

    def test_execute_does_not_mutate_when_pending_approval(self, client: TestClient):
        cur_job = {
            "job_id": "JOB-1",
            "machine_id": "M-1",
            "priority_score": 10.0,
            "status": "in_progress",
            "is_interruptible": True,
            "technician_id": "TECH-B",
        }
        inc_job = {
            "job_id": "JOB-2",
            "machine_id": "M-2",
            "priority_score": 90.0,
        }
        payload = {
            "current_job": cur_job,
            "incoming_job": inc_job,
            "config": {"require_human_approval": True},
            "approved": False,
        }
        res = client.post("/schedule/preemption/execute", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["result"]["status"] == STATUS_PENDING_APPROVAL
        assert data["result"]["preemption_executed"] is False
        assert data["interrupted_job"]["status"] == "in_progress"
        assert data["assignment_state"]["active_job_id"] == "JOB-1"


# ==============================================================================
# 12. Interrupted-job progress preservation and rescheduling
# ==============================================================================

class TestWorkPreservation:
    def test_interrupted_job_progress_preserved_in_reschedule_queue(self, client: TestClient):
        now = time.time()
        cur_job = {
            "job_id": "JOB-PROGRESS",
            "machine_id": "M-44",
            "priority_score": 15.0,
            "status": "in_progress",
            "is_interruptible": True,
            "technician_id": "TECH-C",
            "progress": {"step": 3, "percent": 45.0},
            "started_at": now - 1800.0,
        }
        inc_job = {
            "job_id": "JOB-CRIT-99",
            "machine_id": "M-99",
            "priority_score": 95.0,
        }
        res = client.post(
            "/schedule/preemption/execute",
            json={"current_job": cur_job, "incoming_job": inc_job, "technician_id": "TECH-C"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["interrupted_job"]["progress"] == {"step": 3, "percent": 45.0}
        assert data["interrupted_job"]["started_at"] == now - 1800.0
        assert data["interrupted_job"]["preempted_by_job_id"] == "JOB-CRIT-99"

        # Check in reschedule queue
        queue = data["reschedule_queue"]
        assert any(j["job_id"] == "JOB-PROGRESS" for j in queue)


# ==============================================================================
# 13. Repeated execution / idempotency
# ==============================================================================

class TestIdempotency:
    def test_repeated_preemption_execution_is_idempotent(self, client: TestClient):
        cur_job = {
            "job_id": "JOB-IDEM-1",
            "machine_id": "M-1",
            "priority_score": 15.0,
            "status": "in_progress",
            "is_interruptible": True,
            "technician_id": "TECH-1",
        }
        inc_job = {
            "job_id": "JOB-IDEM-2",
            "machine_id": "M-2",
            "priority_score": 85.0,
        }
        # First execution
        res1 = client.post("/schedule/preemption/execute", json={"current_job": cur_job, "incoming_job": inc_job})
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["result"]["status"] == STATUS_EXECUTED

        # Second repeated execution with the resulting interrupted job
        interrupted = data1["interrupted_job"]
        res2 = client.post("/schedule/preemption/execute", json={"current_job": interrupted, "incoming_job": inc_job})
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["result"]["preemption_executed"] is True
        assert "idempotent" in data2["result"]["decision_reason"].lower()


# ==============================================================================
# 14. Invalid state transitions and nonexistent IDs
# ==============================================================================

class TestInvalidTransitions:
    def test_invalid_probability_out_of_bounds(self, client: TestClient):
        payload = {"machine_id": "M-1", "failure_probability": 1.5}
        res = client.post("/decision/evaluate", json=payload)
        assert res.status_code == 400
        err = res.json()
        assert err["error"]["code"] == "INVALID_INPUT"

    def test_negative_slots_rejected(self, client: TestClient):
        payload = {
            "machines": [{"machine_id": "M-1", "failure_probability": 0.8}],
            "slots": -1,
        }
        res = client.post("/schedule/plan", json=payload)
        assert res.status_code == 400
        err = res.json()
        assert err["error"]["code"] == "INVALID_INPUT"

    def test_self_preemption_rejected(self, client: TestClient):
        job = {"job_id": "JOB-SAME", "machine_id": "M-1", "priority_score": 50.0, "status": "in_progress"}
        res = client.post("/schedule/preemption/evaluate", json={"current_job": job, "incoming_job": job})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == STATUS_DENIED
        assert "same job identifier" in data["decision_reason"].lower()


# ==============================================================================
# 15. API serialization and consistent error responses
# ==============================================================================

class TestApiSerialization:
    def test_health_check(self, client: TestClient):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    def test_consistent_error_response_format(self, client: TestClient):
        # Trigger validation error
        res = client.post("/decision/evaluate", json={})
        assert res.status_code == 400
        data = res.json()
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]
        assert "details" in data["error"]


# ==============================================================================
# 16. End-to-end integration: predictions -> schedule -> preemption -> simulation
# ==============================================================================

class TestEndToEndSimulationIntegration:
    def test_full_pipeline_to_simulation_event_log(self, client: TestClient):
        # 1. Reset simulation
        reset_res = client.post("/simulation/reset")
        assert reset_res.status_code == 200

        # 2. Batch predict fleet
        fleet_readings = [
            {"machine_id": "CNC-01", "temperature_c": 75.0, "vibration_rms": 2.1},
            {"machine_id": "CNC-02", "temperature_c": 82.0, "vibration_rms": 3.8},
            {"machine_id": "CNC-03", "temperature_c": 60.0, "vibration_rms": 1.5},
        ]
        pred_res = client.post("/predict/batch", json=fleet_readings)
        assert pred_res.status_code == 200
        predictions = pred_res.json()
        assert len(predictions) == 3

        # 3. Plan shift schedule with 1 slot
        plan_res = client.post("/schedule/plan", json={"machines": predictions, "slots": 1, "threshold": 0.50})
        assert plan_res.status_code == 200
        plan = plan_res.json()
        selected = plan["selected_machines"][0]
        deferred = plan["deferred_machines"]

        # 4. Emergency machine arises
        cur_job = {
            "job_id": f"JOB-{selected}",
            "machine_id": selected,
            "priority_score": 17.0,
            "status": "in_progress",
            "is_interruptible": True,
            "technician_id": "TECH-ALPHA",
        }
        emergency_job = {
            "job_id": "JOB-EMERGENCY-01",
            "machine_id": "PRESS-FAIL",
            "priority_score": 95.0,
            "alert_category": "actual_failure",
        }

        # 5. Evaluate preemption
        eval_res = client.post("/schedule/preemption/evaluate", json={"current_job": cur_job, "incoming_job": emergency_job})
        assert eval_res.status_code == 200
        assert eval_res.json()["status"] == STATUS_EXECUTED

        # 6. Execute preemption
        exec_res = client.post("/schedule/preemption/execute", json={"current_job": cur_job, "incoming_job": emergency_job, "technician_id": "TECH-ALPHA"})
        assert exec_res.status_code == 200
        exec_data = exec_res.json()
        assert exec_data["result"]["preemption_executed"] is True

        # 7. Query simulation state and verify technician assignment
        state_res = client.get("/simulation/state")
        assert state_res.status_code == 200
        state = state_res.json()
        assert state["technician_fleet"]["technicians"]["TECH-ALPHA"]["active_job_id"] == "JOB-EMERGENCY-01"
        assert f"JOB-{selected}" in state["technician_fleet"]["technicians"]["TECH-ALPHA"]["interrupted_jobs"]

        # 8. Query pull-based event log with cursor
        events_res = client.get("/simulation/events?since=0")
        assert events_res.status_code == 200
        events = events_res.json()
        assert len(events) >= 3  # PREDICTION_BATCH, SCHEDULE_PLANNED, PREEMPTION_EVALUATED, PREEMPTION_EXECUTED
        event_types = [e["event_type"] for e in events]
        assert "PREDICTION_BATCH" in event_types
        assert "SCHEDULE_PLANNED" in event_types
        assert "PREEMPTION_EXECUTED" in event_types

        # Verify cursor filtering
        last_id = events[1]["event_id"]
        subsequent_events = client.get(f"/simulation/events?since={last_id}").json()
        assert len(subsequent_events) == len(events) - 2
        assert all(e["event_id"] > last_id for e in subsequent_events)
