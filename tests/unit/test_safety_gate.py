"""Unit tests for equipment safety gate enforcement."""
import pytest
from app.schemas.common import SafetyOutcome
from app.services.safety_service import SafetyService


@pytest.mark.asyncio
async def test_explicitly_safe_assessment(fresh_state_service, fake_engine_client):
    safety_service = SafetyService(fake_engine_client, fresh_state_service)
    fake_engine_client.safety_outcome = "SAFE_TO_INTERRUPT"

    result = await safety_service.assess_job_safety("JOB-101", "M-01")
    assert result.outcome == SafetyOutcome.SAFE_TO_INTERRUPT
    assert result.is_safe_to_interrupt is True


@pytest.mark.asyncio
async def test_unsafe_assessment(fresh_state_service, fake_engine_client):
    safety_service = SafetyService(fake_engine_client, fresh_state_service)
    fake_engine_client.safety_outcome = "UNSAFE_TO_INTERRUPT"

    result = await safety_service.assess_job_safety("JOB-101", "M-01")
    assert result.outcome == SafetyOutcome.UNSAFE_TO_INTERRUPT
    assert result.is_safe_to_interrupt is False


@pytest.mark.asyncio
async def test_indeterminate_assessment(fresh_state_service, fake_engine_client):
    safety_service = SafetyService(fake_engine_client, fresh_state_service)
    fake_engine_client.safety_outcome = "INDETERMINATE"

    result = await safety_service.assess_job_safety("JOB-101", "M-01")
    assert result.outcome == SafetyOutcome.INDETERMINATE
    assert result.is_safe_to_interrupt is False


@pytest.mark.asyncio
async def test_missing_or_stale_inputs_override_to_unsafe(fresh_state_service, fake_engine_client):
    safety_service = SafetyService(fake_engine_client, fresh_state_service)
    fake_engine_client.safety_outcome = "SAFE_TO_INTERRUPT"
    fake_engine_client.safety_missing = ["hydraulic_pressure_sensor"]

    result = await safety_service.assess_job_safety("JOB-101", "M-01")
    # Even if raw outcome claimed SAFE, missing inputs must strictly force safe=False
    assert result.is_safe_to_interrupt is False
    assert result.outcome == SafetyOutcome.INDETERMINATE


@pytest.mark.asyncio
async def test_safety_fails_closed_on_engine_connection_error(fresh_state_service, fake_engine_client):
    safety_service = SafetyService(fake_engine_client, fresh_state_service)
    fake_engine_client.should_fail_connection = True

    result = await safety_service.assess_job_safety("JOB-101", "M-01")
    assert result.is_safe_to_interrupt is False
    assert result.outcome == SafetyOutcome.INDETERMINATE
