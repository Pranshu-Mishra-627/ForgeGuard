"""Maintenance jobs listing and detail endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.common import JobStatus
from app.schemas.jobs import JobDetailResponse, JobResponse
from app.services.state_service import StateService, get_state_service

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


@router.get("", response_model=List[JobResponse])
async def list_jobs(
    status_filter: Optional[JobStatus] = Query(None, alias="status", description="Filter by job status"),
    machine_id: Optional[str] = Query(None, description="Filter by machine ID"),
    state_service: StateService = Depends(get_state_service),
):
    """List maintenance jobs across supported statuses."""
    jobs = list(state_service.jobs.values())
    if status_filter:
        jobs = [j for j in jobs if j.status == status_filter]
    if machine_id:
        jobs = [j for j in jobs if j.machine_id == machine_id]
    return jobs


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job(
    job_id: str,
    state_service: StateService = Depends(get_state_service),
):
    """Return job details, timeline history, and safety assessment."""
    job = state_service.jobs.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )

    events = state_service.get_events(job_id=job_id, limit=10)
    timeline = [e.model_dump(mode="json") for e in events]

    return JobDetailResponse(
        **job.model_dump(),
        timeline=timeline,
        safety_details={"status": job.safety_status.value},
    )
