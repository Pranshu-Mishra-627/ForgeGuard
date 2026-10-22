"""Machine inventory and detail endpoints."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_prediction_service
from app.schemas.machines import MachineDetailResponse, MachineResponse, TelemetryReading
from app.services.prediction_service import PredictionService
from app.services.state_service import StateService, get_state_service

router = APIRouter(prefix="/api/machines", tags=["Machines"])


@router.get("", response_model=List[MachineResponse])
async def list_machines(
    state_service: StateService = Depends(get_state_service),
):
    """List machines with prediction, decision, safety, and operational fields."""
    return list(state_service.machines.values())


@router.get("/{machine_id}", response_model=MachineDetailResponse)
async def get_machine(
    machine_id: str,
    state_service: StateService = Depends(get_state_service),
):
    """Return machine details, telemetry summary, and recent audit events."""
    machine = state_service.machines.get(machine_id)
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine '{machine_id}' not found",
        )

    # Attach related events
    events = state_service.get_events(machine_id=machine_id, limit=10)
    event_dicts = [e.model_dump(mode="json") for e in events]

    return MachineDetailResponse(
        **machine.model_dump(),
        recent_events=event_dicts,
        equipment_metadata={"critical_station": machine_id in ["M-01", "M-03"]},
    )


@router.post("/{machine_id}/predict", response_model=MachineResponse)
async def submit_machine_reading(
    machine_id: str,
    reading: TelemetryReading,
    prediction_service: PredictionService = Depends(get_prediction_service),
):
    """Submit machine reading, obtain prediction & decision, and update state (Workflow A)."""
    return await prediction_service.predict_single(machine_id, reading)
