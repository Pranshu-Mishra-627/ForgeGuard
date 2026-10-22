"""Preemption service implementing guarded evaluation and atomic execution."""
import logging
from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional

from app.clients.engine_client import EngineClient, EngineConnectionError, EngineTimeoutError
from app.schemas.common import PreemptionDecision, SafetyOutcome
from app.schemas.preemption import (
    PreemptionAlternative,
    PreemptionEvaluateResponse,
    PreemptionExecuteResponse,
)
from app.services.safety_service import SafetyService
from app.services.state_service import StateService, get_state_service

logger = logging.getLogger(__name__)


class PreemptionService:
    """Coordinates preemption evaluation (read-only) and execution (state-mutating)."""

    def __init__(
        self,
        engine_client: Optional[EngineClient] = None,
        state_service: Optional[StateService] = None,
        safety_service: Optional[SafetyService] = None,
    ):
        self.engine_client = engine_client or EngineClient()
        self.state_service = state_service or get_state_service()
        self.safety_service = safety_service or SafetyService(self.engine_client, self.state_service)

    async def evaluate_preemption(
        self,
        current_job_id: str,
        incoming_job_id: str,
        technician_id: str,
    ) -> PreemptionEvaluateResponse:
        """Executes Workflow D: Pre-emption evaluation.

        SAFETY INVARIANT:
        If safety assessment is UNSAFE or INDETERMINATE, evaluation decision is strictly DENY.
        Evaluation NEVER mutates state or assignments.
        """
        # 1. Validate inputs exist in state
        current_job = self.state_service.jobs.get(current_job_id)
        if not current_job:
            raise ValueError(f"Current job '{current_job_id}' does not exist")

        incoming_job = self.state_service.jobs.get(incoming_job_id)
        if not incoming_job:
            raise ValueError(f"Incoming job '{incoming_job_id}' does not exist")

        technician = self.state_service.technicians.get(technician_id)
        if not technician:
            raise ValueError(f"Technician '{technician_id}' does not exist")

        # 2. Hard Safety Gate: Assess safety first
        safety_assessment = await self.safety_service.assess_job_safety(
            job_id=current_job_id,
            machine_id=current_job.machine_id,
        )

        evaluation_id = f"eval-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc)

        # 3. If safety is NOT strictly SAFE_TO_INTERRUPT, DENY immediately
        if not safety_assessment.is_safe_to_interrupt or safety_assessment.outcome != SafetyOutcome.SAFE_TO_INTERRUPT:
            reason_code = f"SAFETY_{safety_assessment.outcome.value}"
            eval_resp = PreemptionEvaluateResponse(
                decision=PreemptionDecision.DENY,
                safe_to_interrupt=False,
                reason_codes=[reason_code],
                explanation=f"Preemption strictly denied by Safety Gate: {safety_assessment.reason}",
                estimated_interruption_cost=None,
                alternatives=[
                    PreemptionAlternative(
                        action="finish_current_job",
                        estimated_total_cost=current_job.estimated_maintenance_cost,
                        feasible=True,
                        reason="Allow current active job to finish safely before servicing new alert.",
                    ),
                    PreemptionAlternative(
                        action="defer_incoming_job",
                        estimated_total_cost=None,
                        feasible=True,
                        reason="Defer incoming job to next shift or secondary technician.",
                    ),
                ],
                evaluation_id=evaluation_id,
                current_job_id=current_job_id,
                incoming_job_id=incoming_job_id,
                safety_outcome=safety_assessment.outcome,
                safety_evidence=safety_assessment.evidence_used,
                missing_signals=safety_assessment.missing_inputs,
                conflicting_signals=safety_assessment.conflicting_signals,
                created_at=now,
                requires_human_approval=False,
            )
            await self.state_service.store_evaluation(eval_resp)
            return eval_resp

        # 4. Safety passed! Call Engine /schedule/preemption/evaluate
        decision = PreemptionDecision.ALLOW
        reason_codes = ["SAFETY_CLEARED"]
        requires_approval = False
        interruption_cost = None
        engine_explanation = "Preemption permitted based on urgency and equipment safety clearance."

        try:
            engine_payload = {
                "current_job_id": current_job_id,
                "incoming_job_id": incoming_job_id,
                "technician_id": technician_id,
                "current_priority": current_job.priority.value,
                "incoming_priority": incoming_job.priority.value,
                "safety_cleared": True,
            }
            engine_eval = await self.engine_client.evaluate_preemption(engine_payload)

            raw_status = engine_eval.get("status", "allow").lower()
            if raw_status in ["deny", "denied", "no_preemption"]:
                decision = PreemptionDecision.DENY
            elif raw_status in ["pending_approval", "needs_review"]:
                decision = PreemptionDecision.NEEDS_REVIEW
                requires_approval = True
            else:
                decision = PreemptionDecision.ALLOW

            requires_approval = engine_eval.get("requires_human_approval", requires_approval)
            if engine_eval.get("reason_codes"):
                reason_codes.extend(engine_eval["reason_codes"])
            if engine_eval.get("decision_reason") or engine_eval.get("reason"):
                engine_explanation = engine_eval.get("decision_reason") or engine_eval.get("reason")
            interruption_cost = engine_eval.get("estimated_interruption_cost") or engine_eval.get("estimated_cost")

        except (EngineConnectionError, EngineTimeoutError) as exc:
            logger.warning(f"Engine preemption evaluate unavailable: {exc}. Reconciling with local policy.")
            # If incoming is critical and current is lower, recommend with human approval required
            if incoming_job.priority.value == "critical" and current_job.priority.value != "critical":
                decision = PreemptionDecision.NEEDS_REVIEW
                requires_approval = True
                engine_explanation = f"Engine unavailable ({exc}); incoming critical job requires manual operator review."
            else:
                decision = PreemptionDecision.DENY
                engine_explanation = f"Engine evaluation unavailable ({exc}); defaulting to safe non-preemption."

        eval_resp = PreemptionEvaluateResponse(
            decision=decision,
            safe_to_interrupt=True,
            reason_codes=reason_codes,
            explanation=engine_explanation,
            estimated_interruption_cost=interruption_cost,
            alternatives=[
                PreemptionAlternative(
                    action="preempt",
                    estimated_total_cost=interruption_cost,
                    feasible=decision != PreemptionDecision.DENY,
                    reason="Preempt active job to handle critical failure risk immediately.",
                ),
                PreemptionAlternative(
                    action="finish_current_job",
                    estimated_total_cost=current_job.estimated_maintenance_cost,
                    feasible=True,
                    reason="Complete active job first to avoid interruption setup penalty.",
                ),
            ],
            evaluation_id=evaluation_id,
            current_job_id=current_job_id,
            incoming_job_id=incoming_job_id,
            safety_outcome=safety_assessment.outcome,
            safety_evidence=safety_assessment.evidence_used,
            missing_signals=safety_assessment.missing_inputs,
            conflicting_signals=safety_assessment.conflicting_signals,
            created_at=now,
            requires_human_approval=requires_approval,
        )

        await self.state_service.store_evaluation(eval_resp)

        self.state_service.record_event(
            event_type="preemption_evaluated",
            job_id=current_job_id,
            technician_id=technician_id,
            outcome=decision.value,
            reason=engine_explanation,
            severity="info" if decision == PreemptionDecision.ALLOW else "warning",
            details={
                "evaluation_id": evaluation_id,
                "incoming_job_id": incoming_job_id,
                "safe_to_interrupt": True,
                "requires_approval": requires_approval,
            },
        )

        return eval_resp

    async def execute_preemption(
        self,
        current_job_id: str,
        evaluation_id: str,
        incoming_job_id: str,
        approval_granted: bool = False,
    ) -> PreemptionExecuteResponse:
        """Executes Workflow E: Pre-emption execution.

        Re-validates safety and state, calls Engine /schedule/preemption/execute,
        and atomically transitions canonical state.
        """
        # 1. Fetch evaluation record
        eval_record = self.state_service.evaluations.get(evaluation_id)
        if not eval_record:
            raise ValueError(f"Evaluation '{evaluation_id}' is invalid or expired")

        if eval_record.current_job_id != current_job_id:
            raise ValueError(
                f"Evaluation target job '{eval_record.current_job_id}' does not match path job '{current_job_id}'"
            )

        if eval_record.incoming_job_id != incoming_job_id:
            raise ValueError(
                f"Evaluation incoming job '{eval_record.incoming_job_id}' does not match '{incoming_job_id}'"
            )

        # 2. Hard safety gate check
        if not eval_record.safe_to_interrupt or eval_record.safety_outcome != SafetyOutcome.SAFE_TO_INTERRUPT:
            raise ValueError("Preemption execution blocked: equipment safety assessment was NOT safe")

        if eval_record.decision == PreemptionDecision.DENY:
            raise ValueError("Preemption execution blocked: evaluation decision was DENY")

        if eval_record.requires_human_approval and not approval_granted:
            raise ValueError("Preemption execution blocked: supervisor approval is required but was not granted")

        current_job = self.state_service.jobs.get(current_job_id)
        if not current_job or current_job.status.value != "in_progress":
            raise ValueError(f"Current job '{current_job_id}' is not in progress; evaluation is stale")

        technician_id = current_job.technician_id
        if not technician_id:
            raise ValueError(f"Current job '{current_job_id}' has no assigned technician")

        # 3. Call Engine /schedule/preemption/execute
        try:
            engine_payload = {
                "evaluation_id": evaluation_id,
                "current_job_id": current_job_id,
                "incoming_job_id": incoming_job_id,
                "technician_id": technician_id,
                "approval_granted": approval_granted,
            }
            # State-changing call: DO NOT blindly retry on timeout
            engine_res = await self.engine_client.execute_preemption(engine_payload)
            logger.info(f"Engine confirmed preemption execute: {engine_res}")
        except (EngineConnectionError, EngineTimeoutError) as exc:
            logger.warning(f"Engine preemption execution call failed: {exc}. Processing with verified local invariants.")

        # 4. Execute atomic state transition in state service
        await self.state_service.execute_preemption_state_transition(
            evaluation_id=evaluation_id,
            incoming_job_id=incoming_job_id,
            approval_granted=approval_granted,
        )

        now = datetime.now(timezone.utc)
        return PreemptionExecuteResponse(
            success=True,
            status="executed",
            preemption_executed=True,
            interrupted_job_id=current_job_id,
            incoming_job_id=incoming_job_id,
            technician_id=technician_id,
            executed_at=now,
            message=f"Preemption confirmed. Interrupted {current_job_id} (progress preserved), dispatched {technician_id} to {incoming_job_id}.",
        )
