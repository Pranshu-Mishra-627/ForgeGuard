"""Emergency preemption evaluation and execution endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_preemption_service
from app.schemas.preemption import (
    PreemptionEvaluateRequest,
    PreemptionEvaluateResponse,
    PreemptionExecuteRequest,
    PreemptionExecuteResponse,
)
from app.services.preemption_service import PreemptionService

router = APIRouter(prefix="/api/jobs", tags=["Preemption"])


@router.post("/{job_id}/preemption/evaluate", response_model=PreemptionEvaluateResponse)
async def evaluate_preemption(
    job_id: str,
    request: PreemptionEvaluateRequest,
    preemption_service: PreemptionService = Depends(get_preemption_service),
):
    """Evaluate whether an active job can be safely interrupted for an urgent incoming job.

    CRITICAL INVARIANT:
    Evaluation is purely diagnostic and NEVER mutates job assignments or technician states.
    Equipment safety is a hard gate.
    """
    try:
        return await preemption_service.evaluate_preemption(
            current_job_id=job_id,
            incoming_job_id=request.incoming_job_id,
            technician_id=request.technician_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/{job_id}/preemption/execute", response_model=PreemptionExecuteResponse)
async def execute_preemption(
    job_id: str,
    request: PreemptionExecuteRequest,
    preemption_service: PreemptionService = Depends(get_preemption_service),
):
    """Execute a previously evaluated preemption after re-validating safety and state freshness.

    CRITICAL INVARIANT:
    Execution re-validates that safety was strictly SAFE_TO_INTERRUPT and state is fresh.
    Preserves interrupted job's elapsed progress.
    """
    try:
        return await preemption_service.execute_preemption(
            current_job_id=job_id,
            evaluation_id=request.evaluation_id,
            incoming_job_id=request.incoming_job_id,
            approval_granted=request.approval_granted,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
