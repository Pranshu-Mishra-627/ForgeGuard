"""Simulation service managing demo/replay lifecycle and scenario controls."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.clients.engine_client import EngineClient, EngineConnectionError, EngineTimeoutError
from app.schemas.common import JobPriority, JobStatus, MachineDecision, MachineStatus, SafetyStatus, SimulationMode, SimulationStatus
from app.schemas.jobs import JobResponse
from app.schemas.simulation import (
    SimulationActionResponse,
    SimulationInjectFailureRequest,
    SimulationStartRequest,
    SimulationStateResponse,
    SimulationStepRequest,
)
from app.services.state_service import StateService, get_state_service

logger = logging.getLogger(__name__)


class SimulationService:
    """Coordinates simulation progression, scenario execution, and event syncing."""

    def __init__(self, engine_client: Optional[EngineClient] = None, state_service: Optional[StateService] = None):
        self.engine_client = engine_client or EngineClient()
        self.state_service = state_service or get_state_service()

    async def get_state(self) -> SimulationStateResponse:
        """Returns normalized simulation state."""
        return self.state_service.simulation_state

    async def start(self, request: SimulationStartRequest) -> SimulationActionResponse:
        """Starts simulation replay/demo mode."""
        now = datetime.now(timezone.utc)
        self.state_service.simulation_state = self.state_service.simulation_state.model_copy(
            update={
                "status": SimulationStatus.RUNNING,
                "mode": request.mode,
                "speed": request.speed,
                "last_updated_at": now,
            }
        )

        self.state_service.record_event(
            event_type="simulation_started",
            outcome="running",
            reason=f"Started {request.mode.value} scenario '{request.scenario_id}' at {request.speed}x speed",
            severity="info",
            details={"mode": request.mode.value, "speed": request.speed, "scenario_id": request.scenario_id},
        )

        return SimulationActionResponse(
            success=True,
            message="Simulation started successfully",
            state=self.state_service.simulation_state,
        )

    async def pause(self) -> SimulationActionResponse:
        """Pauses simulation progression."""
        now = datetime.now(timezone.utc)
        self.state_service.simulation_state = self.state_service.simulation_state.model_copy(
            update={
                "status": SimulationStatus.PAUSED,
                "last_updated_at": now,
            }
        )

        self.state_service.record_event(
            event_type="simulation_paused",
            outcome="paused",
            reason="Simulation paused by operator",
            severity="info",
        )

        return SimulationActionResponse(
            success=True,
            message="Simulation paused",
            state=self.state_service.simulation_state,
        )

    async def resume(self) -> SimulationActionResponse:
        """Resumes paused simulation."""
        now = datetime.now(timezone.utc)
        self.state_service.simulation_state = self.state_service.simulation_state.model_copy(
            update={
                "status": SimulationStatus.RUNNING,
                "last_updated_at": now,
            }
        )

        self.state_service.record_event(
            event_type="simulation_resumed",
            outcome="running",
            reason="Simulation resumed by operator",
            severity="info",
        )

        return SimulationActionResponse(
            success=True,
            message="Simulation resumed",
            state=self.state_service.simulation_state,
        )

    async def step(self, request: SimulationStepRequest) -> SimulationActionResponse:
        """Advances simulation by requested ticks/steps."""
        seconds_to_advance = request.steps * 60
        new_state = await self.state_service.update_simulation_clock(seconds_to_advance)

        self.state_service.record_event(
            event_type="simulation_stepped",
            outcome="stepped",
            reason=f"Advanced {request.steps} simulation step(s) ({seconds_to_advance}s)",
            severity="info",
            details={"steps": request.steps, "total_steps": new_state.step},
        )

        return SimulationActionResponse(
            success=True,
            message=f"Simulation advanced by {request.steps} step(s)",
            state=new_state,
        )

    async def reset(self) -> SimulationActionResponse:
        """Resets simulation and operational state to documented baseline."""
        # 1. Clear local state
        self.state_service.reset_to_baseline()

        # 2. Reset engine simulation state if engine is connected
        try:
            await self.engine_client.reset_simulation()
            logger.info("Decision engine simulation state reset confirmed")
        except (EngineConnectionError, EngineTimeoutError) as exc:
            logger.warning(f"Engine simulation reset skipped (engine unreachable): {exc}")

        self.state_service.record_event(
            event_type="simulation_reset",
            outcome="reset",
            reason="Simulation and state reset to canonical baseline",
            severity="info",
        )

        return SimulationActionResponse(
            success=True,
            message="Simulation reset to baseline successfully",
            state=self.state_service.simulation_state,
        )

    async def inject_failure(self, request: SimulationInjectFailureRequest) -> SimulationActionResponse:
        """Triggers clearly-labeled demo scenario failure on target machine."""
        machine_id = request.machine_id
        target = self.state_service.machines.get(machine_id)
        if not target:
            raise ValueError(f"Target machine '{machine_id}' does not exist")

        now = self.state_service.simulation_state.simulated_at

        # 1. Update machine to critical failure status
        updated_telemetry = dict(target.telemetry or {})
        updated_telemetry["torque"] = 68.5  # abnormal torque
        updated_telemetry["tool_wear"] = 240.0  # worn tool

        critical_machine = target.model_copy(
            update={
                "status": MachineStatus.CRITICAL,
                "failure_probability": 0.96,
                "predicted_failure_mode": "PWF",  # Power Failure
                "decision": MachineDecision.URGENT_MAINTENANCE,
                "last_telemetry_at": now,
                "safety_status": SafetyStatus.SAFE,  # Safe to stop equipment
                "telemetry": updated_telemetry,
            }
        )
        self.state_service.machines[machine_id] = critical_machine

        # 2. Generate urgent incoming maintenance job for preemption scenario
        urgent_job_id = f"JOB-URGENT-{machine_id}"
        urgent_job = JobResponse(
            job_id=urgent_job_id,
            machine_id=machine_id,
            job_type="corrective",
            priority=JobPriority.CRITICAL,
            status=JobStatus.QUEUED,
            technician_id=None,
            estimated_duration_minutes=90,
            elapsed_minutes=0,
            progress_percent=0,
            estimated_maintenance_cost=1200.0,
            estimated_downtime_cost=4500.0,
            safety_status=SafetyStatus.SAFE,
            created_at=now,
            updated_at=now,
            pause_reason=None,
        )
        self.state_service.jobs[urgent_job_id] = urgent_job

        # 3. Record confirmed demo failure event
        self.state_service.record_event(
            event_type="failure_injected",
            machine_id=machine_id,
            job_id=urgent_job_id,
            outcome="critical_failure_injected",
            reason=f"DEMO SCENARIO: Injected {request.scenario} on {machine_id}. Generated critical job {urgent_job_id}",
            severity="critical",
            details={
                "scenario": request.scenario,
                "generated_job_id": urgent_job_id,
                "failure_probability": 0.96,
            },
        )

        return SimulationActionResponse(
            success=True,
            message=f"DEMO SCENARIO: Injected failure on {machine_id}. Created critical job {urgent_job_id}.",
            state=self.state_service.simulation_state,
        )
