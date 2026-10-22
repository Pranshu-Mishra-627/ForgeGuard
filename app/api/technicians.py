"""Technician workforce status and availability endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query

from app.schemas.common import TechnicianStatus
from app.schemas.technicians import TechnicianResponse
from app.services.state_service import StateService, get_state_service

router = APIRouter(prefix="/api/technicians", tags=["Technicians"])


@router.get("", response_model=List[TechnicianResponse])
async def list_technicians(
    status_filter: Optional[TechnicianStatus] = Query(None, alias="status", description="Filter by availability"),
    state_service: StateService = Depends(get_state_service),
):
    """Return technician availability, assignments, skills, and workload."""
    techs = list(state_service.technicians.values())
    if status_filter:
        techs = [t for t in techs if t.status == status_filter]
    return techs
