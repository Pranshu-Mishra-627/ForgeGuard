"""Simulation lifecycle and demo scenario control endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_simulation_service
from app.schemas.simulation import (
    SimulationActionResponse,
    SimulationInjectFailureRequest,
    SimulationStartRequest,
    SimulationStateResponse,
    SimulationStepRequest,
)
from app.services.simulation_service import SimulationService

router = APIRouter(prefix="/api/simulation", tags=["Simulation"])


@router.get("/state", response_model=SimulationStateResponse)
async def get_simulation_state(
    simulation_service: SimulationService = Depends(get_simulation_service),
):
    """Retrieve normalized simulation clock and execution state."""
    return await simulation_service.get_state()


@router.post("/start", response_model=SimulationActionResponse)
async def start_simulation(
    request: SimulationStartRequest = SimulationStartRequest(),
    simulation_service: SimulationService = Depends(get_simulation_service),
):
    """Start simulation replay or demo scenario."""
    return await simulation_service.start(request)


@router.post("/pause", response_model=SimulationActionResponse)
async def pause_simulation(
    simulation_service: SimulationService = Depends(get_simulation_service),
):
    """Pause ongoing simulation."""
    return await simulation_service.pause()


@router.post("/resume", response_model=SimulationActionResponse)
async def resume_simulation(
    simulation_service: SimulationService = Depends(get_simulation_service),
):
    """Resume paused simulation progression."""
    return await simulation_service.resume()


@router.post("/step", response_model=SimulationActionResponse)
async def step_simulation(
    request: SimulationStepRequest = SimulationStepRequest(),
    simulation_service: SimulationService = Depends(get_simulation_service),
):
    """Advance simulation by requested ticks/steps."""
    return await simulation_service.step(request)


@router.post("/reset", response_model=SimulationActionResponse)
async def reset_simulation(
    simulation_service: SimulationService = Depends(get_simulation_service),
):
    """Reset simulation and state back to canonical baseline."""
    return await simulation_service.reset()


@router.post("/inject-failure", response_model=SimulationActionResponse)
async def inject_failure(
    request: SimulationInjectFailureRequest,
    simulation_service: SimulationService = Depends(get_simulation_service),
):
    """Trigger a clearly-labeled scenario failure for live demonstration."""
    try:
        return await simulation_service.inject_failure(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
