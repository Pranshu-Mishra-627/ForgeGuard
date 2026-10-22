"""End-to-end workflow integration tests: readings -> predictions -> decisions -> schedule -> safety -> preemption -> refresh."""
import pytest


def test_end_to_end_full_pipeline(client):
    # 1. Start simulation
    res_start = client.post("/api/simulation/start", json={"mode": "replay", "speed": 1.0})
    assert res_start.status_code == 200

    # 2. Ingest sensor reading for Machine M-03
    reading = {
        "air_temperature": 300.2,
        "process_temperature": 310.5,
        "rotational_speed": 1350,
        "torque": 65.0,
        "tool_wear": 230,
        "machine_type": "H",
    }
    res_pred = client.post("/api/machines/M-03/predict", json=reading)
    assert res_pred.status_code == 200
    m3_data = res_pred.json()
    assert m3_data["failure_probability"] > 0.5
    assert m3_data["status"] == "critical"

    # 3. Trigger schedule replan to incorporate new risk
    res_replan = client.post("/api/schedule/replan", json={"reason": "critical_reading_M03"})
    assert res_replan.status_code == 200
    sched = res_replan.json()
    assert "assignments" in sched

    # 4. Inject urgent failure to create urgent job on M-03
    res_inj = client.post(
        "/api/simulation/inject-failure",
        json={"machine_id": "M-03", "scenario": "power_failure"},
    )
    assert res_inj.status_code == 200

    # 5. Evaluate preemption for active job JOB-101 with incoming emergency job
    eval_req = {
        "incoming_job_id": "JOB-URGENT-M-03",
        "technician_id": "TECH-01",
    }
    res_eval = client.post("/api/jobs/JOB-101/preemption/evaluate", json=eval_req)
    assert res_eval.status_code == 200
    eval_resp = res_eval.json()
    assert eval_resp["safe_to_interrupt"] is True
    eval_id = eval_resp["evaluation_id"]

    # 6. Execute preemption
    exec_req = {
        "evaluation_id": eval_id,
        "incoming_job_id": "JOB-URGENT-M-03",
        "approval_granted": True,
    }
    res_exec = client.post("/api/jobs/JOB-101/preemption/execute", json=exec_req)
    assert res_exec.status_code == 200
    exec_data = res_exec.json()
    assert exec_data["status"] == "executed"
    assert exec_data["interrupted_job_id"] == "JOB-101"

    # 7. Verify UI view refresh consistency
    # Interrupted job is paused with progress preserved
    res_j101 = client.get("/api/jobs/JOB-101")
    assert res_j101.json()["status"] == "paused"
    assert res_j101.json()["progress_percent"] == 41

    # Urgent job is in_progress and assigned to TECH-01
    res_urg = client.get("/api/jobs/JOB-URGENT-M-03")
    assert res_urg.json()["status"] == "in_progress"
    assert res_urg.json()["technician_id"] == "TECH-01"

    # Technician 01 is assigned to urgent job
    res_techs = client.get("/api/technicians")
    tech_01 = next(t for t in res_techs.json() if t["technician_id"] == "TECH-01")
    assert tech_01["current_job_id"] == "JOB-URGENT-M-03"

    # Event log reflects the entire chain
    res_events = client.get("/api/events")
    events = res_events.json()["events"]
    event_types = [e["event_type"] for e in events]
    assert "preemption_executed" in event_types
    assert "failure_injected" in event_types
