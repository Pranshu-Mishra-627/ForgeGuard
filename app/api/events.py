"""Audit and operational event trail endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, Query

from app.schemas.events import EventsResponse
from app.services.state_service import StateService, get_state_service

router = APIRouter(prefix="/api/events", tags=["Events"])


@router.get("", response_model=EventsResponse)
async def list_events(
    since: Optional[str] = Query(None, description="Cursor or event ID to retrieve events since"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of events to return"),
    machine_id: Optional[str] = Query(None, description="Filter by machine ID"),
    job_id: Optional[str] = Query(None, description="Filter by job ID"),
    severity: Optional[str] = Query(None, description="Filter by severity: info, warning, critical"),
    state_service: StateService = Depends(get_state_service),
):
    """Return normalized audit and simulation event history with filtering and pagination."""
    events = state_service.get_events(
        since=since,
        limit=limit,
        machine_id=machine_id,
        job_id=job_id,
        severity=severity,
    )
    cursor = events[-1].event_id if events else None

    return EventsResponse(
        events=events,
        total=len(events),
        cursor=cursor,
    )
