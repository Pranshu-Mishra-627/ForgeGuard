"""Shift schedule planning and replanning endpoints."""
from fastapi import APIRouter, Depends

from app.api.dependencies import get_scheduling_service
from app.schemas.schedule import ReplanRequest, ScheduleResponse
from app.services.scheduling_service import SchedulingService

router = APIRouter(prefix="/api/schedule", tags=["Schedule"])


@router.get("", response_model=ScheduleResponse)
async def get_schedule(
    scheduling_service: SchedulingService = Depends(get_scheduling_service),
):
    """Return the current active schedule and assignments."""
    return await scheduling_service.get_current_schedule()


@router.post("/replan", response_model=ScheduleResponse)
async def replan_schedule(
    request: ReplanRequest = ReplanRequest(),
    scheduling_service: SchedulingService = Depends(get_scheduling_service),
):
    """Recompute the schedule through the engine and synchronize the resulting state."""
    return await scheduling_service.replan_schedule(request)
