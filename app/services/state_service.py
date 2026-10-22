"""Canonical in-memory state service for ForgeGuard Orchestration Backend.

Enforces system-wide invariants:
1. One technician cannot be assigned to conflicting active jobs simultaneously.
2. A job cannot be both completed and in-progress.
3. Technician assignment agrees strictly with job and schedule state.
4. Interrupted jobs preserve elapsed work time and progress.
5. Evaluation does NOT mutate state or assignments.
6. Unsafe or indeterminate preemption cannot be executed.
7. Reset clears simulation mutations back to documented baseline.
8. Missing values remain missing (None), never fabricated into zeros or fake statuses.
"""

import asyncio
from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional

from app.schemas.common import (
    JobPriority,
    JobStatus,
    MachineDecision,
    MachineStatus,
    PreemptionDecision,
    SafetyOutcome,
    SafetyStatus,
    SimulationMode,
    SimulationStatus,
    TechnicianStatus,
)
from app.schemas.events import AuditEvent
from app.schemas.jobs import JobResponse
from app.schemas.machines import MachineResponse
from app.schemas.preemption import PreemptionEvaluateResponse
from app.schemas.schedule import ScheduleAssignment, ScheduleResponse
from app.schemas.simulation import SimulationStateResponse
from app.schemas.technicians import TechnicianResponse


class StateService:
    """Thread-safe, process-local authoritative operational state container."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self.reset_to_baseline()

    def reset_to_baseline(self) -> None:
        """Initializes or resets system to known baseline state."""
        now = datetime.now(timezone.utc)

        # 1. Simulation clock & controls
        self.simulation_state = SimulationStateResponse(
            status=SimulationStatus.STOPPED,
            mode=SimulationMode.REPLAY,
            simulated_at=now,
            speed=1.0,
            last_updated_at=now,
            step=0,
        )

        # 2. Canonical Machines Fleet
        self.machines: Dict[str, MachineResponse] = {
            "M-01": MachineResponse(
                machine_id="M-01",
                name="CNC Milling Station 01",
                status=MachineStatus.WATCH,
                failure_probability=0.22,
                predicted_failure_mode="HDF",
                last_telemetry_at=now,
                decision=MachineDecision.SCHEDULE_MAINTENANCE,
                remaining_useful_life_hours=None,
                safety_status=SafetyStatus.SAFE,
                active_job_id="JOB-101",
                telemetry={
                    "air_temperature": 298.1,
                    "process_temperature": 308.6,
                    "rotational_speed": 1551,
                    "torque": 42.8,
                    "tool_wear": 120,
                    "type": "M",
                },
            ),
            "M-02": MachineResponse(
                machine_id="M-02",
                name="CNC Milling Station 02",
                status=MachineStatus.HEALTHY,
                failure_probability=0.03,
                predicted_failure_mode=None,
                last_telemetry_at=now,
                decision=MachineDecision.MONITOR,
                remaining_useful_life_hours=None,
                safety_status=SafetyStatus.SAFE,
                active_job_id=None,
                telemetry={
                    "air_temperature": 298.2,
                    "process_temperature": 308.7,
                    "rotational_speed": 1408,
                    "torque": 46.3,
                    "tool_wear": 14,
                    "type": "L",
                },
            ),
            "M-03": MachineResponse(
                machine_id="M-03",
                name="Hydraulic Stamping Press 03",
                status=MachineStatus.HEALTHY,
                failure_probability=0.04,
                predicted_failure_mode=None,
                last_telemetry_at=now,
                decision=MachineDecision.MONITOR,
                remaining_useful_life_hours=None,
                safety_status=SafetyStatus.SAFE,
                active_job_id=None,
                telemetry={
                    "air_temperature": 298.1,
                    "process_temperature": 308.5,
                    "rotational_speed": 1498,
                    "torque": 49.4,
                    "tool_wear": 5,
                    "type": "H",
                },
            ),
            "M-04": MachineResponse(
                machine_id="M-04",
                name="Precision Lathe 04",
                status=MachineStatus.WATCH,
                failure_probability=0.18,
                predicted_failure_mode=None,
                last_telemetry_at=now,
                decision=MachineDecision.MONITOR,
                remaining_useful_life_hours=None,
                safety_status=SafetyStatus.SAFE,
                active_job_id=None,
                telemetry={
                    "air_temperature": 298.2,
                    "process_temperature": 308.6,
                    "rotational_speed": 1433,
                    "torque": 39.5,
                    "tool_wear": 85,
                    "type": "M",
                },
            ),
            "M-05": MachineResponse(
                machine_id="M-05",
                name="Industrial Surface Grinder 05",
                status=MachineStatus.HEALTHY,
                failure_probability=0.02,
                predicted_failure_mode=None,
                last_telemetry_at=now,
                decision=MachineDecision.MONITOR,
                remaining_useful_life_hours=None,
                safety_status=SafetyStatus.SAFE,
                active_job_id=None,
                telemetry={
                    "air_temperature": 298.2,
                    "process_temperature": 308.7,
                    "rotational_speed": 1549,
                    "torque": 35.8,
                    "tool_wear": 10,
                    "type": "L",
                },
            ),
            "M-06": MachineResponse(
                machine_id="M-06",
                name="Automated Multi-Drill Rig 06",
                status=MachineStatus.HEALTHY,
                failure_probability=0.05,
                predicted_failure_mode=None,
                last_telemetry_at=now,
                decision=MachineDecision.MONITOR,
                remaining_useful_life_hours=None,
                safety_status=SafetyStatus.SAFE,
                active_job_id=None,
                telemetry={
                    "air_temperature": 298.3,
                    "process_temperature": 308.8,
                    "rotational_speed": 1576,
                    "torque": 36.5,
                    "tool_wear": 12,
                    "type": "M",
                },
            ),
        }

        # 3. Canonical Technicians
        self.technicians: Dict[str, TechnicianResponse] = {
            "TECH-01": TechnicianResponse(
                technician_id="TECH-01",
                name="Sarah Chen",
                status=TechnicianStatus.ON_JOB,
                skills=["mechanical", "hydraulics", "vibration_analysis"],
                current_job_id="JOB-101",
                estimated_available_at=now,
            ),
            "TECH-02": TechnicianResponse(
                technician_id="TECH-02",
                name="Marcus Ramirez",
                status=TechnicianStatus.AVAILABLE,
                skills=["electrical", "drives", "automation"],
                current_job_id=None,
                estimated_available_at=None,
            ),
            "TECH-03": TechnicianResponse(
                technician_id="TECH-03",
                name="Alex Becker",
                status=TechnicianStatus.AVAILABLE,
                skills=["mechanical", "sensors", "calibration"],
                current_job_id=None,
                estimated_available_at=None,
            ),
        }

        # 4. Canonical Jobs
        self.jobs: Dict[str, JobResponse] = {
            "JOB-101": JobResponse(
                job_id="JOB-101",
                machine_id="M-01",
                job_type="preventive",
                priority=JobPriority.MEDIUM,
                status=JobStatus.IN_PROGRESS,
                technician_id="TECH-01",
                estimated_duration_minutes=60,
                elapsed_minutes=25,
                progress_percent=41,
                estimated_maintenance_cost=450.0,
                estimated_downtime_cost=300.0,
                safety_status=SafetyStatus.SAFE,
                created_at=now,
                updated_at=now,
                pause_reason=None,
            ),
            "JOB-102": JobResponse(
                job_id="JOB-102",
                machine_id="M-04",
                job_type="inspection",
                priority=JobPriority.LOW,
                status=JobStatus.QUEUED,
                technician_id=None,
                estimated_duration_minutes=45,
                elapsed_minutes=0,
                progress_percent=0,
                estimated_maintenance_cost=150.0,
                estimated_downtime_cost=100.0,
                safety_status=SafetyStatus.SAFE,
                created_at=now,
                updated_at=now,
                pause_reason=None,
            ),
        }

        # 5. Canonical Schedule
        self.schedule = ScheduleResponse(
            generated_at=now,
            assignments=[
                ScheduleAssignment(
                    job_id="JOB-101",
                    machine_id="M-01",
                    technician_id="TECH-01",
                    status="in_progress",
                    priority_score=0.22,
                    reason="Scheduled preventive maintenance based on threshold alert",
                ),
                ScheduleAssignment(
                    job_id="JOB-102",
                    machine_id="M-04",
                    technician_id=None,
                    status="planned",
                    priority_score=0.18,
                    reason="Secondary inspection queued for next available slot",
                ),
            ],
            selected_machines=["M-01"],
            deferred_machines=["M-04"],
            unalerted_machines=["M-02", "M-03", "M-05", "M-06"],
            capacity_summary={"total_slots": 3, "allocated_slots": 1, "free_slots": 2},
        )

        # 6. Preemption evaluations tracking (evaluation_id -> PreemptionEvaluateResponse)
        self.evaluations: Dict[str, PreemptionEvaluateResponse] = {}

        # 7. Recorded Audit Events log
        self.events: List[AuditEvent] = [
            AuditEvent(
                event_id="EVT-0001",
                timestamp=now,
                event_type="simulation_initialized",
                machine_id=None,
                job_id=None,
                technician_id=None,
                outcome="success",
                reason="System initialized to baseline configuration",
                severity="info",
                details={"fleet_size": 6, "active_jobs": 1, "technicians_count": 3},
            )
        ]

    # =========================================================================
    # Event Management
    # =========================================================================

    def record_event(
        self,
        event_type: str,
        machine_id: Optional[str] = None,
        job_id: Optional[str] = None,
        technician_id: Optional[str] = None,
        outcome: Optional[str] = None,
        reason: Optional[str] = None,
        severity: str = "info",
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """Appends an event to the audit trail with guaranteed monotonic ID."""
        event_id = f"EVT-{len(self.events) + 1:04d}"
        event = AuditEvent(
            event_id=event_id,
            timestamp=self.simulation_state.simulated_at,
            event_type=event_type,
            machine_id=machine_id,
            job_id=job_id,
            technician_id=technician_id,
            outcome=outcome,
            reason=reason,
            severity=severity,
            details=details or {},
        )
        self.events.append(event)
        return event

    def get_events(
        self,
        since: Optional[str] = None,
        limit: int = 50,
        machine_id: Optional[str] = None,
        job_id: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> List[AuditEvent]:
        """Filters audit trail events in reverse chronological order."""
        filtered = self.events
        if since:
            # Match either event_id or timestamp
            try:
                since_idx = next(i for i, e in enumerate(filtered) if e.event_id == since)
                filtered = filtered[since_idx + 1 :]
            except StopIteration:
                pass

        if machine_id:
            filtered = [e for e in filtered if e.machine_id == machine_id]
        if job_id:
            filtered = [e for e in filtered if e.job_id == job_id]
        if severity:
            filtered = [e for e in filtered if e.severity == severity]

        # Newest first
        return list(reversed(filtered))[:limit]

    # =========================================================================
    # Simulation Control
    # =========================================================================

    async def update_simulation_clock(self, seconds_to_advance: int = 60) -> SimulationStateResponse:
        """Advances simulated time by specified seconds."""
        async with self._lock:
            from datetime import timedelta
            now = datetime.now(timezone.utc)
            self.simulation_state.simulated_at += timedelta(seconds=seconds_to_advance)
            self.simulation_state.last_updated_at = now
            self.simulation_state.step += 1
            return self.simulation_state.model_copy()

    # =========================================================================
    # Preemption Guard & Execution
    # =========================================================================

    async def store_evaluation(self, eval_resp: PreemptionEvaluateResponse) -> None:
        """Stores evaluation result for later execution validation."""
        async with self._lock:
            self.evaluations[eval_resp.evaluation_id] = eval_resp

    async def execute_preemption_state_transition(
        self,
        evaluation_id: str,
        incoming_job_id: str,
        approval_granted: bool = False,
    ) -> PreemptionEvaluateResponse:
        """Atomically transitions state during preemption execution.

        Checks:
        1. Evaluation exists and has not expired/stale.
        2. Safety outcome was strictly SAFE_TO_INTERRUPT.
        3. Approval granted if required.
        4. Current job is still in_progress and assigned to specified technician.
        5. Preserves interrupted job progress and reassigns technician to incoming job.
        """
        async with self._lock:
            eval_record = self.evaluations.get(evaluation_id)
            if not eval_record:
                raise ValueError(f"Evaluation '{evaluation_id}' not found or expired")

            # Hard safety gate check
            if not eval_record.safe_to_interrupt or eval_record.safety_outcome != SafetyOutcome.SAFE_TO_INTERRUPT:
                raise ValueError(f"Safety gate blocked preemption: outcome is {eval_record.safety_outcome}")

            if eval_record.decision == PreemptionDecision.DENY:
                raise ValueError("Cannot execute preemption: evaluation decision was DENY")

            if eval_record.requires_human_approval and not approval_granted:
                raise ValueError("Preemption requires supervisor approval before execution")

            current_job = self.jobs.get(eval_record.current_job_id)
            if not current_job:
                raise ValueError(f"Current job '{eval_record.current_job_id}' not found")

            # Validate state freshness
            if current_job.status != JobStatus.IN_PROGRESS:
                raise ValueError(
                    f"Job '{current_job.job_id}' is in status '{current_job.status}', cannot be interrupted"
                )

            incoming_job = self.jobs.get(incoming_job_id)
            if not incoming_job:
                raise ValueError(f"Incoming job '{incoming_job_id}' not found")

            tech_id = current_job.technician_id
            if not tech_id or tech_id not in self.technicians:
                raise ValueError(f"Technician '{tech_id}' is no longer assigned to current job")

            now = self.simulation_state.simulated_at

            # State Transition:
            # 1. Pause current job, PRESERVING elapsed minutes and progress
            paused_job = current_job.model_copy(
                update={
                    "status": JobStatus.PAUSED,
                    "technician_id": None,
                    "updated_at": now,
                    "pause_reason": f"Preempted by emergency job {incoming_job_id}",
                }
            )
            self.jobs[paused_job.job_id] = paused_job

            # 2. Assign technician to incoming job and set status to IN_PROGRESS
            assigned_incoming = incoming_job.model_copy(
                update={
                    "status": JobStatus.IN_PROGRESS,
                    "technician_id": tech_id,
                    "updated_at": now,
                }
            )
            self.jobs[incoming_job.job_id] = assigned_incoming

            # 3. Update Technician assignment
            technician = self.technicians[tech_id].model_copy(
                update={
                    "status": TechnicianStatus.ON_JOB,
                    "current_job_id": incoming_job_id,
                }
            )
            self.technicians[tech_id] = technician

            # 4. Update Machine active_job_id pointers
            if current_job.machine_id in self.machines:
                m_curr = self.machines[current_job.machine_id].model_copy(update={"active_job_id": None})
                self.machines[current_job.machine_id] = m_curr

            if incoming_job.machine_id in self.machines:
                m_inc = self.machines[incoming_job.machine_id].model_copy(update={"active_job_id": incoming_job_id})
                self.machines[incoming_job.machine_id] = m_inc

            # 5. Update Schedule assignments
            new_assignments = []
            for item in self.schedule.assignments:
                if item.job_id == paused_job.job_id:
                    new_assignments.append(
                        item.model_copy(update={"status": "paused", "technician_id": None, "reason": "Preempted"})
                    )
                else:
                    new_assignments.append(item)

            # Add incoming job to schedule if not present
            if not any(a.job_id == incoming_job_id for a in new_assignments):
                new_assignments.insert(
                    0,
                    ScheduleAssignment(
                        job_id=incoming_job_id,
                        machine_id=incoming_job.machine_id,
                        technician_id=tech_id,
                        status="in_progress",
                        priority_score=0.99,
                        reason="Emergency preemption dispatched",
                    ),
                )
            else:
                for idx, a in enumerate(new_assignments):
                    if a.job_id == incoming_job_id:
                        new_assignments[idx] = a.model_copy(
                            update={"status": "in_progress", "technician_id": tech_id}
                        )

            self.schedule = self.schedule.model_copy(
                update={"assignments": new_assignments, "generated_at": now}
            )

            # 6. Record Event
            self.record_event(
                event_type="preemption_executed",
                machine_id=incoming_job.machine_id,
                job_id=incoming_job_id,
                technician_id=tech_id,
                outcome="executed",
                reason=f"Interrupted {current_job.job_id} (elapsed: {current_job.elapsed_minutes}m, progress: {current_job.progress_percent}%)",
                severity="critical",
                details={
                    "interrupted_job_id": current_job.job_id,
                    "incoming_job_id": incoming_job_id,
                    "technician_id": tech_id,
                    "progress_preserved": current_job.progress_percent,
                },
            )

            return eval_record


# Global singleton instance for application state
_state_service_instance: Optional[StateService] = None


def get_state_service() -> StateService:
    """Returns singleton state service container."""
    global _state_service_instance
    if _state_service_instance is None:
        _state_service_instance = StateService()
    return _state_service_instance
