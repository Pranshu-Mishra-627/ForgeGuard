"""Simulation schemas for UI lifecycle and demo controls."""
from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas.common import SimulationMode, SimulationStatus


class SimulationStartRequest(BaseModel):
    mode: SimulationMode = Field(default=SimulationMode.REPLAY, description="Simulation mode (replay, demo, or live)")
    speed: float = Field(default=1.0, ge=0.1, le=100.0, description="Simulation clock speed multiplier")
    scenario_id: str = Field(default="baseline", description="Demo or replay scenario identifier")


class SimulationStepRequest(BaseModel):
    steps: int = Field(default=1, ge=1, le=1000, description="Number of simulation steps/ticks to advance")


class SimulationInjectFailureRequest(BaseModel):
    machine_id: str = Field(..., description="Target machine identifier for scenario failure injection")
    scenario: str = Field(default="critical_failure", description="Scenario type (e.g., critical_failure, power_loss)")


class SimulationStateResponse(BaseModel):
    status: SimulationStatus = Field(..., description="Simulation execution status: running, paused, stopped")
    mode: SimulationMode = Field(..., description="Simulation mode: replay, demo, live")
    simulated_at: datetime = Field(..., description="Current simulated wall clock timestamp (ISO-8601)")
    speed: float = Field(default=1.0, description="Current simulation speed factor")
    last_updated_at: datetime = Field(..., description="Real-time timestamp of last state change (ISO-8601)")
    step: int = Field(default=0, description="Cumulative simulation step counter")


class SimulationActionResponse(BaseModel):
    success: bool
    message: str
    state: SimulationStateResponse
