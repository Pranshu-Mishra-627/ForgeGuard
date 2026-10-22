"""Safety service enforcing the uncompromised equipment safety gate."""
import logging
from typing import Any, Dict, List, Optional

from app.clients.engine_client import EngineClient, EngineConnectionError, EngineTimeoutError
from app.schemas.common import SafetyOutcome, SafetyStatus
from app.services.state_service import StateService, get_state_service

logger = logging.getLogger(__name__)


class SafetyAssessmentResult:
    """Encapsulates the engine's equipment safety assessment."""
    def __init__(
        self,
        outcome: SafetyOutcome,
        is_safe_to_interrupt: bool,
        evidence_used: List[str],
        missing_inputs: List[str],
        stale_signals: List[str],
        conflicting_signals: List[str],
        reason: str,
    ):
        self.outcome = outcome
        self.is_safe_to_interrupt = is_safe_to_interrupt
        self.evidence_used = evidence_used
        self.missing_inputs = missing_inputs
        self.stale_signals = stale_signals
        self.conflicting_signals = conflicting_signals
        self.reason = reason


class SafetyService:
    """Enforces equipment safety before allowing any operational preemption."""

    def __init__(self, engine_client: Optional[EngineClient] = None, state_service: Optional[StateService] = None):
        self.engine_client = engine_client or EngineClient()
        self.state_service = state_service or get_state_service()

    async def assess_job_safety(self, job_id: str, machine_id: str) -> SafetyAssessmentResult:
        """Calls Engine /safety/assess and strictly enforces safety invariants.

        CRITICAL RULE:
        Missing, stale, conflicting, or indeterminate safety evidence is NEVER safe.
        """
        machine = self.state_service.machines.get(machine_id)
        telemetry = machine.telemetry if machine else {}

        payload = {
            "job_id": job_id,
            "machine_id": machine_id,
            "telemetry": telemetry,
            "equipment_type": telemetry.get("type", "M") if telemetry else "M",
        }

        try:
            raw_res = await self.engine_client.assess_safety(payload)
            outcome_str = raw_res.get("outcome", "INDETERMINATE").upper()

            if outcome_str == "SAFE_TO_INTERRUPT":
                outcome = SafetyOutcome.SAFE_TO_INTERRUPT
                is_safe = True
            elif outcome_str == "UNSAFE_TO_INTERRUPT":
                outcome = SafetyOutcome.UNSAFE_TO_INTERRUPT
                is_safe = False
            else:
                outcome = SafetyOutcome.INDETERMINATE
                is_safe = False

            # Explicit check for missing, stale, or conflicting signals
            missing = raw_res.get("missing_inputs", [])
            stale = raw_res.get("stale_signals", [])
            conflicts = raw_res.get("conflicting_signals", [])

            # Hard safety override: If there are missing, stale, or conflicting signals,
            # never allow safe_to_interrupt=True!
            if missing or stale or conflicts:
                outcome = SafetyOutcome.INDETERMINATE
                is_safe = False

            reason = raw_res.get("reason", f"Safety assessment result: {outcome.value}")

        except (EngineConnectionError, EngineTimeoutError) as exc:
            logger.warning(f"Engine safety assessment call failed: {exc}")
            # Network partition or engine failure MUST fail closed to UNSAFE / INDETERMINATE!
            outcome = SafetyOutcome.INDETERMINATE
            is_safe = False
            missing = ["engine_connection"]
            stale = []
            conflicts = []
            reason = f"Safety service unreachable ({exc}). Defaulting to INDETERMINATE for equipment protection."

        # Update job and machine safety status
        if is_safe:
            status_val = SafetyStatus.SAFE
        elif outcome == SafetyOutcome.UNSAFE_TO_INTERRUPT:
            status_val = SafetyStatus.UNSAFE
        else:
            status_val = SafetyStatus.INDETERMINATE

        if job_id in self.state_service.jobs:
            self.state_service.jobs[job_id] = self.state_service.jobs[job_id].model_copy(
                update={"safety_status": status_val}
            )

        if machine_id in self.state_service.machines:
            self.state_service.machines[machine_id] = self.state_service.machines[machine_id].model_copy(
                update={"safety_status": status_val}
            )

        self.state_service.record_event(
            event_type="safety_assessment_completed",
            machine_id=machine_id,
            job_id=job_id,
            outcome=outcome.value,
            reason=reason,
            severity="info" if is_safe else "warning",
            details={
                "is_safe_to_interrupt": is_safe,
                "missing_inputs": missing,
                "stale_signals": stale,
                "conflicting_signals": conflicts,
            },
        )

        return SafetyAssessmentResult(
            outcome=outcome,
            is_safe_to_interrupt=is_safe,
            evidence_used=raw_res.get("evidence_used", ["telemetry_inspection"]) if "raw_res" in locals() else [],
            missing_inputs=missing,
            stale_signals=stale,
            conflicting_signals=conflicts,
            reason=reason,
        )
