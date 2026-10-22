"""Unit tests for StateService invariants and transitions."""
import pytest
from app.schemas.common import JobStatus, MachineStatus, TechnicianStatus
from app.services.state_service import StateService


def test_baseline_state_initialization():
    service = StateService()
    assert len(service.machines) == 6
    assert len(service.technicians) == 3
    assert len(service.jobs) >= 2
    assert service.simulation_state.status.value == "stopped"

    # Test stable IDs
    assert "M-01" in service.machines
    assert "TECH-01" in service.technicians
    assert "JOB-101" in service.jobs


def test_invariants_technician_job_agreement():
    service = StateService()
    job_101 = service.jobs["JOB-101"]
    tech_01 = service.technicians["TECH-01"]

    # Technician 01 is assigned to JOB-101
    assert job_101.technician_id == "TECH-01"
    assert tech_01.current_job_id == "JOB-101"
    assert tech_01.status == TechnicianStatus.ON_JOB


def test_missing_values_remain_missing():
    service = StateService()
    # RUL is unsupported and must remain None, NOT 0 or fabricated number
    m1 = service.machines["M-01"]
    assert m1.remaining_useful_life_hours is None


def test_event_recording_and_filtering():
    service = StateService()
    initial_count = len(service.events)

    service.record_event(
        event_type="test_event",
        machine_id="M-01",
        job_id="JOB-101",
        outcome="success",
        severity="info",
    )

    assert len(service.events) == initial_count + 1
    events = service.get_events(machine_id="M-01")
    assert any(e.event_type == "test_event" for e in events)


def test_reset_semantics():
    service = StateService()
    # Mutate machine
    service.machines["M-01"] = service.machines["M-01"].model_copy(update={"status": MachineStatus.CRITICAL})
    assert service.machines["M-01"].status == MachineStatus.CRITICAL

    # Reset
    service.reset_to_baseline()
    assert service.machines["M-01"].status == MachineStatus.WATCH
