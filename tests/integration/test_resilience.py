"""Resilience and failure-recovery integration tests."""
import pytest
from app.clients.engine_client import EngineConnectionError, EngineTimeoutError


def test_engine_offline_at_startup_service_still_healthy(client, fake_engine_client):
    # Engine is offline
    fake_engine_client.should_fail_connection = True

    # 1. Health check still succeeds
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"

    # 2. Status gracefully reports engine disconnected
    res_status = client.get("/api/status")
    assert res_status.status_code == 200
    assert res_status.json()["dependencies"]["engine"]["status"] == "disconnected"


def test_engine_goes_offline_during_replan_preserves_old_schedule(client, fake_engine_client):
    # Get initial valid schedule
    initial_sched = client.get("/api/schedule").json()

    # Engine drops connection
    fake_engine_client.should_fail_connection = True

    # Replan attempted
    res_replan = client.post("/api/schedule/replan", json={"reason": "replan_while_down"})
    assert res_replan.status_code == 200
    replan_data = res_replan.json()

    # Must preserve previous schedule assignments!
    assert len(replan_data["assignments"]) == len(initial_sched["assignments"])


def test_engine_timeout_safety_assessment_fails_closed(client, fake_engine_client):
    # Engine times out on safety
    fake_engine_client.should_timeout = True

    eval_req = {
        "incoming_job_id": "JOB-102",
        "technician_id": "TECH-01",
    }
    # Preemption evaluate must fail closed to DENY because safety could not be verified
    res_eval = client.post("/api/jobs/JOB-101/preemption/evaluate", json=eval_req)
    assert res_eval.status_code == 200
    data = res_eval.json()
    assert data["safe_to_interrupt"] is False
    assert data["decision"] == "deny"


def test_recovery_after_engine_reconnects(client, fake_engine_client):
    # 1. Engine offline
    fake_engine_client.should_fail_connection = True
    assert client.get("/api/status").json()["dependencies"]["engine"]["status"] == "disconnected"

    # 2. Engine reconnects
    fake_engine_client.should_fail_connection = False
    assert client.get("/api/status").json()["dependencies"]["engine"]["status"] == "connected"

    # 3. Operations succeed normally
    res = client.post("/api/schedule/replan", json={"reason": "recovered"})
    assert res.status_code == 200
