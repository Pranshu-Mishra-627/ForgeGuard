"""Contract tests covering all 13 Decision Engine routes from ForgeGuard_HTTP_Endpoints_Reference.txt."""
import json
import pytest
import httpx

from app.clients.engine_client import (
    EngineClient,
    EngineConnectionError,
    EngineResponseError,
    EngineTimeoutError,
)


@pytest.fixture
def mock_http_transport():
    """Captures outgoing HTTP requests and provides canned responses for contract testing."""
    captured_requests = []

    def handler(request: httpx.Request):
        captured_requests.append(request)
        path = request.url.path
        method = request.method

        if path == "/health" and method == "GET":
            return httpx.Response(200, json={"status": "ok"})
        elif path == "/predict" and method == "POST":
            return httpx.Response(200, json={
                "machine_id": "M-01",
                "failure_probability": 0.35,
                "predicted_failure_mode": "HDF",
                "maintenance_alert": True,
                "prediction_timestamp": "2026-10-22T10:00:00Z",
                "model_version": "v1.2",
            })
        elif path == "/predict/batch" and method == "POST":
            return httpx.Response(200, json={
                "predictions": [
                    {"machine_id": "M-01", "failure_probability": 0.35},
                    {"machine_id": "M-02", "failure_probability": 0.05},
                ]
            })
        elif path == "/decision/evaluate" and method == "POST":
            return httpx.Response(200, json={
                "machine_id": "M-01",
                "alert_decision": "schedule_maintenance",
                "threshold_used": 0.25,
            })
        elif path == "/decision/threshold" and method == "GET":
            return httpx.Response(200, json={
                "optimal_threshold": 0.27,
                "optimal_cost": 1420.0,
                "confusion_matrix": {"tp": 40, "tn": 950, "fp": 8, "fn": 2},
            })
        elif path == "/decision/threshold" and method == "POST":
            return httpx.Response(200, json={"optimal_threshold": 0.26, "status": "optimized"})
        elif path == "/schedule/plan" and method == "POST":
            return httpx.Response(200, json={
                "selected_machines": ["M-01"],
                "deferred_machines": [],
                "unalerted_machines": ["M-02"],
                "assignments": [{"job_id": "J-1", "machine_id": "M-01", "technician_id": "TECH-01"}],
            })
        elif path == "/safety/assess" and method == "POST":
            return httpx.Response(200, json={
                "outcome": "SAFE_TO_INTERRUPT",
                "is_safe_to_interrupt": True,
                "evidence_used": ["axis_parked"],
                "missing_inputs": [],
                "stale_signals": [],
                "conflicting_signals": [],
                "reason": "Clear to interrupt",
            })
        elif path == "/schedule/preemption/evaluate" and method == "POST":
            return httpx.Response(200, json={
                "status": "allow",
                "preemption_executed": False,
                "requires_human_approval": False,
                "interrupted_job_id": "JOB-101",
                "incoming_job_id": "JOB-102",
                "decision_reason": "Urgent alert priority",
            })
        elif path == "/schedule/preemption/execute" and method == "POST":
            return httpx.Response(200, json={
                "status": "executed",
                "preemption_executed": True,
                "interrupted_job_id": "JOB-101",
                "incoming_job_id": "JOB-102",
                "technician_id": "TECH-01",
            })
        elif path == "/simulation/state" and method == "GET":
            return httpx.Response(200, json={
                "status": "running",
                "simulated_at": "2026-10-22T10:00:00Z",
                "speed": 1.0,
            })
        elif path == "/simulation/events" and method == "GET":
            return httpx.Response(200, json={"events": []})
        elif path == "/simulation/reset" and method == "POST":
            return httpx.Response(200, json={"status": "reset", "message": "Reset complete"})

        return httpx.Response(404, json={"detail": "Not found"})

    transport = httpx.MockTransport(handler)
    return transport, captured_requests


@pytest.fixture
async def contract_client(mock_http_transport):
    transport, captured = mock_http_transport
    client = EngineClient(base_url="http://engine-contract-test:8001")
    # Inject mock transport into client
    client._client = httpx.AsyncClient(
        base_url="http://engine-contract-test:8001",
        transport=transport,
    )
    yield client, captured
    await client.close()


# 1) GET /health
@pytest.mark.asyncio
async def test_contract_01_get_health(contract_client):
    client, captured = contract_client
    res = await client.get_health()
    assert res["status"] == "ok"
    assert captured[-1].method == "GET"
    assert captured[-1].url.path == "/health"


# 2) POST /predict
@pytest.mark.asyncio
async def test_contract_02_post_predict(contract_client):
    client, captured = contract_client
    payload = {"machine_id": "M-01", "air_temperature": 298.1}
    res = await client.predict(payload)
    assert res["machine_id"] == "M-01"
    assert captured[-1].method == "POST"
    assert captured[-1].url.path == "/predict"
    assert json.loads(captured[-1].content) == payload


# 3) POST /predict/batch
@pytest.mark.asyncio
async def test_contract_03_post_predict_batch(contract_client):
    client, captured = contract_client
    readings = [{"machine_id": "M-01"}, {"machine_id": "M-02"}]
    res = await client.predict_batch(readings)
    assert "predictions" in res
    assert captured[-1].method == "POST"
    assert captured[-1].url.path == "/predict/batch"


# 4) POST /decision/evaluate
@pytest.mark.asyncio
async def test_contract_04_post_decision_evaluate(contract_client):
    client, captured = contract_client
    payload = {"machine_id": "M-01", "failure_probability": 0.35}
    res = await client.evaluate_decision(payload)
    assert res["alert_decision"] == "schedule_maintenance"
    assert captured[-1].method == "POST"
    assert captured[-1].url.path == "/decision/evaluate"


# 5) GET /decision/threshold
@pytest.mark.asyncio
async def test_contract_05_get_decision_threshold(contract_client):
    client, captured = contract_client
    res = await client.get_threshold()
    assert res["optimal_threshold"] == 0.27
    assert captured[-1].method == "GET"
    assert captured[-1].url.path == "/decision/threshold"


# 6) POST /decision/threshold
@pytest.mark.asyncio
async def test_contract_06_post_decision_threshold(contract_client):
    client, captured = contract_client
    res = await client.optimize_threshold({"cost_fp": 50.0, "cost_fn": 500.0})
    assert res["optimal_threshold"] == 0.26
    assert captured[-1].method == "POST"
    assert captured[-1].url.path == "/decision/threshold"


# 7) POST /schedule/plan
@pytest.mark.asyncio
async def test_contract_07_post_schedule_plan(contract_client):
    client, captured = contract_client
    payload = {"machines": [{"machine_id": "M-01"}], "slots": 2}
    res = await client.plan_schedule(payload)
    assert res["selected_machines"] == ["M-01"]
    assert captured[-1].method == "POST"
    assert captured[-1].url.path == "/schedule/plan"


# 8) POST /safety/assess
@pytest.mark.asyncio
async def test_contract_08_post_safety_assess(contract_client):
    client, captured = contract_client
    payload = {"job_id": "JOB-101", "machine_id": "M-01"}
    res = await client.assess_safety(payload)
    assert res["outcome"] == "SAFE_TO_INTERRUPT"
    assert captured[-1].method == "POST"
    assert captured[-1].url.path == "/safety/assess"


# 9) POST /schedule/preemption/evaluate
@pytest.mark.asyncio
async def test_contract_09_post_preemption_evaluate(contract_client):
    client, captured = contract_client
    payload = {"current_job_id": "JOB-101", "incoming_job_id": "JOB-102", "technician_id": "TECH-01"}
    res = await client.evaluate_preemption(payload)
    assert res["status"] == "allow"
    assert captured[-1].method == "POST"
    assert captured[-1].url.path == "/schedule/preemption/evaluate"


# 10) POST /schedule/preemption/execute
@pytest.mark.asyncio
async def test_contract_10_post_preemption_execute(contract_client):
    client, captured = contract_client
    payload = {"current_job_id": "JOB-101", "incoming_job_id": "JOB-102", "technician_id": "TECH-01"}
    res = await client.execute_preemption(payload)
    assert res["status"] == "executed"
    assert captured[-1].method == "POST"
    assert captured[-1].url.path == "/schedule/preemption/execute"


# 11) GET /simulation/state
@pytest.mark.asyncio
async def test_contract_11_get_simulation_state(contract_client):
    client, captured = contract_client
    res = await client.get_simulation_state()
    assert res["status"] == "running"
    assert captured[-1].method == "GET"
    assert captured[-1].url.path == "/simulation/state"


# 12) GET /simulation/events
@pytest.mark.asyncio
async def test_contract_12_get_simulation_events(contract_client):
    client, captured = contract_client
    res = await client.get_simulation_events(since="EVT-01", limit=10)
    assert "events" in res
    assert captured[-1].method == "GET"
    assert captured[-1].url.path == "/simulation/events"
    assert captured[-1].url.params["since"] == "EVT-01"
    assert captured[-1].url.params["limit"] == "10"


# 13) POST /simulation/reset
@pytest.mark.asyncio
async def test_contract_13_post_simulation_reset(contract_client):
    client, captured = contract_client
    res = await client.reset_simulation()
    assert res["status"] == "reset"
    assert captured[-1].method == "POST"
    assert captured[-1].url.path == "/simulation/reset"
