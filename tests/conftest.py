"""Pytest shared test configuration, fixtures, and fake engine mock."""
import pytest
from typing import Any, Dict, List, Optional

from fastapi.testclient import TestClient

from app.api.dependencies import get_engine_client, get_state_service
from app.clients.engine_client import EngineClient, EngineConnectionError, EngineTimeoutError
from app.main import app
from app.services.state_service import StateService


class FakeEngineClient(EngineClient):
    """Deterministic in-memory test double for Decision Engine HTTP service."""

    def __init__(self):
        super().__init__(base_url="http://mock-engine:8001", timeout=5.0, retry_attempts=1)
        self.should_fail_connection = False
        self.should_timeout = False
        self.safety_outcome = "SAFE_TO_INTERRUPT"
        self.safety_missing = []
        self.safety_stale = []
        self.safety_conflicts = []
        self.preemption_status = "allow"
        self.preemption_requires_approval = False
        self.call_history: List[Dict[str, Any]] = []

    def _record_call(self, endpoint: str, payload: Any = None):
        self.call_history.append({"endpoint": endpoint, "payload": payload})
        if self.should_fail_connection:
            raise EngineConnectionError("Mock: Engine unreachable")
        if self.should_timeout:
            raise EngineTimeoutError("Mock: Request timed out")

    async def get_health(self) -> Dict[str, Any]:
        self._record_call("GET /health")
        return {"status": "ok", "service": "mock-decision-engine", "version": "1.0.0"}

    async def predict(self, reading: Dict[str, Any]) -> Dict[str, Any]:
        self._record_call("POST /predict", reading)
        prob = 0.85 if reading.get("tool_wear", 0) > 200 else 0.15
        return {
            "machine_id": reading.get("machine_id", "M-01"),
            "failure_probability": prob,
            "predicted_failure_mode": "TWF" if prob > 0.5 else None,
            "maintenance_alert": prob > 0.25,
            "prediction_timestamp": "2026-10-22T10:00:00Z",
            "model_version": "v1.2",
        }

    async def predict_batch(self, readings: List[Dict[str, Any]]) -> Dict[str, Any]:
        self._record_call("POST /predict/batch", readings)
        batch = readings if isinstance(readings, list) else readings.get("machines", [])
        results = []
        for r in batch:
            m_id = r.get("machine_id", "M-01")
            prob = 0.75 if m_id in ["M-01", "M-03"] else 0.05
            results.append({
                "machine_id": m_id,
                "failure_probability": prob,
                "predicted_failure_mode": "HDF" if prob > 0.5 else None,
                "maintenance_alert": prob > 0.25,
            })
        return {"predictions": results}

    async def evaluate_decision(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._record_call("POST /decision/evaluate", payload)
        prob = payload.get("failure_probability", 0.0)
        decision = "urgent_maintenance" if prob >= 0.7 else ("schedule_maintenance" if prob >= 0.2 else "monitor")
        return {
            "machine_id": payload.get("machine_id", "M-01"),
            "alert_decision": decision,
            "threshold_used": 0.25,
            "cost_breakdown": {"fp_penalty": 50.0, "fn_penalty": 500.0},
        }

    async def get_threshold(self) -> Dict[str, Any]:
        self._record_call("GET /decision/threshold")
        return {
            "optimal_threshold": 0.27,
            "optimal_cost": 1420.0,
            "baseline_cost": 3800.0,
            "cost_fp": 50.0,
            "cost_fn": 500.0,
            "confusion_matrix": {"tp": 42, "tn": 950, "fp": 8, "fn": 3},
        }

    async def optimize_threshold(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._record_call("POST /decision/threshold", payload)
        return {
            "optimal_threshold": 0.26,
            "optimal_cost": 1390.0,
            "status": "optimized",
        }

    async def plan_schedule(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._record_call("POST /schedule/plan", payload)
        machines = payload.get("machines", [])
        slots = payload.get("slots", 3)
        # Select alerted machines up to slots
        selected = [m["machine_id"] for m in machines if m.get("failure_probability", 0) >= 0.2][:slots]
        deferred = [m["machine_id"] for m in machines if m.get("failure_probability", 0) >= 0.2][slots:]
        unalerted = [m["machine_id"] for m in machines if m.get("failure_probability", 0) < 0.2]
        return {
            "selected_machines": selected,
            "deferred_machines": deferred,
            "unalerted_machines": unalerted,
            "schedule_table": [
                {
                    "job_id": f"JOB-SCHED-{m_id}",
                    "machine_id": m_id,
                    "technician_id": f"TECH-0{idx+1}" if idx < slots else None,
                    "status": "planned",
                    "priority_score": 0.9 - (idx * 0.1),
                    "reason": f"Dispatched by engine priority #{idx+1}",
                }
                for idx, m_id in enumerate(selected)
            ],
            "audit_summary": {"slots": slots, "selected_count": len(selected)},
        }

    async def assess_safety(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._record_call("POST /safety/assess", payload)
        is_safe = self.safety_outcome == "SAFE_TO_INTERRUPT" and not (
            self.safety_missing or self.safety_stale or self.safety_conflicts
        )
        return {
            "outcome": self.safety_outcome,
            "is_safe_to_interrupt": is_safe,
            "evidence_used": ["telemetry_pressure_normal", "axis_parked"],
            "missing_inputs": self.safety_missing,
            "stale_signals": self.safety_stale,
            "conflicting_signals": self.safety_conflicts,
            "reason": f"Mock engine assessed safety outcome: {self.safety_outcome}",
        }

    async def evaluate_preemption(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._record_call("POST /schedule/preemption/evaluate", payload)
        return {
            "status": self.preemption_status,
            "preemption_executed": False,
            "requires_human_approval": self.preemption_requires_approval,
            "interrupted_job_id": payload.get("current_job_id"),
            "incoming_job_id": payload.get("incoming_job_id"),
            "decision_reason": f"Mock engine evaluation result: {self.preemption_status}",
            "estimated_interruption_cost": 250.0,
            "reason_codes": [f"PREEMPT_{self.preemption_status.upper()}"],
        }

    async def execute_preemption(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._record_call("POST /schedule/preemption/execute", payload)
        return {
            "status": "executed",
            "preemption_executed": True,
            "interrupted_job_id": payload.get("current_job_id"),
            "incoming_job_id": payload.get("incoming_job_id"),
            "technician_id": payload.get("technician_id"),
        }

    async def get_simulation_state(self) -> Dict[str, Any]:
        self._record_call("GET /simulation/state")
        return {
            "status": "running",
            "simulated_at": "2026-10-22T10:00:00Z",
            "speed": 1.0,
            "step": 42,
        }

    async def get_simulation_events(self, since: Any = 0, limit: int = 50) -> Dict[str, Any]:
        self._record_call("GET /simulation/events", {"since": since, "limit": limit})
        return {
            "events": [
                {
                    "event_id": "EVT-ENG-01",
                    "timestamp": "2026-10-22T10:00:00Z",
                    "event_type": "engine_cycle",
                    "details": {"step": 42},
                }
            ]
        }

    async def reset_simulation(self) -> Dict[str, Any]:
        self._record_call("POST /simulation/reset")
        return {"status": "reset", "message": "Engine simulation reset successfully"}


@pytest.fixture
def fresh_state_service():
    """Provides an isolated in-memory StateService."""
    service = StateService()
    return service


@pytest.fixture
def fake_engine_client():
    """Provides a fresh fake engine client."""
    return FakeEngineClient()


@pytest.fixture
def client(fresh_state_service, fake_engine_client):
    """Provides FastAPI TestClient wired to test state and mock engine."""
    app.dependency_overrides[get_state_service] = lambda: fresh_state_service
    app.dependency_overrides[get_engine_client] = lambda: fake_engine_client
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
