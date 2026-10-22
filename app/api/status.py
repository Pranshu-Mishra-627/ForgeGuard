"""Orchestration and dependency status endpoint."""
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import get_engine_client
from app.clients.engine_client import EngineClient
from app.config import get_settings
from app.services.state_service import StateService, get_state_service

router = APIRouter(prefix="/api", tags=["Status"])


class DependencyStatus(BaseModel):
    status: str
    url: str
    details: Optional[Any] = None


class SystemStatusResponse(BaseModel):
    orchestration: Dict[str, Any]
    simulation: Dict[str, Any]
    dependencies: Dict[str, Any]


@router.get("/status", response_model=SystemStatusResponse)
async def system_status(
    engine_client: EngineClient = Depends(get_engine_client),
    state_service: StateService = Depends(get_state_service),
):
    """Detailed orchestration and upstream dependency connectivity report."""
    settings = get_settings()

    # Check Engine connectivity gracefully
    engine_connected = False
    engine_details = None
    try:
        health_res = await engine_client.get_health()
        engine_connected = True
        engine_details = health_res
    except Exception as exc:
        engine_details = str(exc)

    sim_state = state_service.simulation_state

    return SystemStatusResponse(
        orchestration={
            "status": "operational",
            "environment": settings.environment,
            "version": "1.0.0",
            "machines_monitored": len(state_service.machines),
            "active_jobs": sum(1 for j in state_service.jobs.values() if j.status.value == "in_progress"),
            "technicians_count": len(state_service.technicians),
        },
        simulation={
            "status": sim_state.status.value,
            "mode": sim_state.mode.value,
            "simulated_at": sim_state.simulated_at.isoformat(),
            "speed": sim_state.speed,
            "step": sim_state.step,
        },
        dependencies={
            "engine": {
                "status": "connected" if engine_connected else "disconnected",
                "base_url": engine_client.base_url,
                "details": engine_details,
            }
        },
    )
