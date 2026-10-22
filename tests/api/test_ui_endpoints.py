"""API integration tests covering all UI-facing endpoints."""
import pytest


def test_get_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "forgeguard-orchestration"


def test_get_status(client):
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert "orchestration" in data
    assert "simulation" in data
    assert "dependencies" in data
    assert data["dependencies"]["engine"]["status"] == "connected"


def test_machines_endpoints(client):
    # List machines
    res = client.get("/api/machines")
    assert res.status_code == 200
    machines = res.json()
    assert len(machines) == 6
    assert any(m["machine_id"] == "M-01" for m in machines)

    # Get single machine details
    res_m1 = client.get("/api/machines/M-01")
    assert res_m1.status_code == 200
    m1 = res_m1.json()
    assert m1["machine_id"] == "M-01"
    assert "recent_events" in m1

    # 404 for non-existent machine
    res_404 = client.get("/api/machines/M-999")
    assert res_404.status_code == 404
    err = res_404.json()
    assert err["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_machine_predict_flow(client):
    reading = {
        "air_temperature": 298.5,
        "process_temperature": 308.9,
        "rotational_speed": 1500,
        "torque": 40.0,
        "tool_wear": 220,
        "machine_type": "M",
    }
    res = client.post("/api/machines/M-01/predict", json=reading)
    assert res.status_code == 200
    data = res.json()
    assert data["machine_id"] == "M-01"
    assert data["failure_probability"] is not None


def test_jobs_endpoints(client):
    res = client.get("/api/jobs")
    assert res.status_code == 200
    jobs = res.json()
    assert len(jobs) >= 2

    res_j1 = client.get("/api/jobs/JOB-101")
    assert res_j1.status_code == 200
    j1 = res_j1.json()
    assert j1["job_id"] == "JOB-101"
    assert j1["status"] == "in_progress"
    assert "timeline" in j1


def test_technicians_endpoints(client):
    res = client.get("/api/technicians")
    assert res.status_code == 200
    techs = res.json()
    assert len(techs) == 3
    assert any(t["technician_id"] == "TECH-01" for t in techs)


def test_schedule_endpoints(client):
    res = client.get("/api/schedule")
    assert res.status_code == 200
    sched = res.json()
    assert "assignments" in sched
    assert len(sched["assignments"]) >= 1

    # Replan
    res_replan = client.post("/api/schedule/replan", json={"reason": "test_replan"})
    assert res_replan.status_code == 200
    replan_data = res_replan.json()
    assert "assignments" in replan_data


def test_preemption_endpoints(client):
    # 1. Evaluate preemption
    eval_req = {
        "incoming_job_id": "JOB-102",
        "technician_id": "TECH-01",
    }
    res_eval = client.post("/api/jobs/JOB-101/preemption/evaluate", json=eval_req)
    assert res_eval.status_code == 200
    eval_data = res_eval.json()
    assert eval_data["safe_to_interrupt"] is True
    assert eval_data["decision"] in ["allow", "needs_review"]
    eval_id = eval_data["evaluation_id"]

    # 2. Execute preemption
    exec_req = {
        "evaluation_id": eval_id,
        "incoming_job_id": "JOB-102",
        "approval_granted": True,
    }
    res_exec = client.post("/api/jobs/JOB-101/preemption/execute", json=exec_req)
    assert res_exec.status_code == 200
    exec_data = res_exec.json()
    assert exec_data["success"] is True
    assert exec_data["status"] == "executed"
    assert exec_data["interrupted_job_id"] == "JOB-101"


def test_events_endpoint(client):
    res = client.get("/api/events")
    assert res.status_code == 200
    data = res.json()
    assert "events" in data
    assert data["total"] >= 1


def test_cost_analysis_endpoint(client):
    res = client.get("/api/cost-analysis")
    assert res.status_code == 200
    data = res.json()
    assert "currency" in data
    assert "options" in data
    assert data["cost_data_available"] is True


def test_simulation_lifecycle_endpoints(client):
    # Start
    res_start = client.post("/api/simulation/start", json={"mode": "replay", "speed": 1.0})
    assert res_start.status_code == 200
    assert res_start.json()["state"]["status"] == "running"

    # Step
    res_step = client.post("/api/simulation/step", json={"steps": 2})
    assert res_step.status_code == 200
    assert res_step.json()["state"]["step"] == 1

    # Pause
    res_pause = client.post("/api/simulation/pause")
    assert res_pause.status_code == 200
    assert res_pause.json()["state"]["status"] == "paused"

    # Resume
    res_resume = client.post("/api/simulation/resume")
    assert res_resume.status_code == 200
    assert res_resume.json()["state"]["status"] == "running"

    # Inject failure
    res_inj = client.post(
        "/api/simulation/inject-failure",
        json={"machine_id": "M-03", "scenario": "critical_failure"},
    )
    assert res_inj.status_code == 200

    # Reset
    res_reset = client.post("/api/simulation/reset")
    assert res_reset.status_code == 200
    assert res_reset.json()["state"]["status"] == "stopped"


def test_validation_error_response_format(client):
    # Malformed request body
    res = client.post("/api/simulation/step", json={"steps": -5})
    assert res.status_code == 422
    err = res.json()
    assert "error" in err
    assert err["error"]["code"] == "VALIDATION_ERROR"
    assert "request_id" in err
