"""Simulation state store and pull-based event logger for ForgeGuard.

Maintains live simulation state:
- Monotonic simulation clock and timestamp tracking
- Fleet machine states and recent telemetry readings
- Active technician work orders and assignments
- Reschedule queue for interrupted jobs
- Append-only pull-based event log with cursor retrieval (?since=<cursor>)
"""

from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


@dataclass
class SimulationEvent:
    """An auditable simulation event record.

    Attributes:
        event_id: Monotonically increasing sequence number.
        timestamp: Unix epoch timestamp in seconds.
        timestamp_iso: ISO-8601 formatted UTC timestamp string.
        event_type: Classification (e.g. 'PREDICTION', 'ALERT_EVALUATED', 'SCHEDULE_PLANNED',
                    'SAFETY_ASSESSED', 'PREEMPTION_EVALUATED', 'PREEMPTION_EXECUTED').
        machine_id: Relevant machine identifier, if applicable.
        job_id: Relevant maintenance job identifier, if applicable.
        technician_id: Relevant technician identifier, if applicable.
        outcome: Action outcome or decision status.
        reason: Plain-English explanation or rationale.
        before_state: State snapshot reference prior to event execution.
        after_state: State snapshot reference after event execution.
        metadata: Arbitrary operational context metadata.
    """

    event_id: int
    timestamp: float
    timestamp_iso: str
    event_type: str
    machine_id: str | None = None
    job_id: str | None = None
    technician_id: str | None = None
    outcome: str = "SUCCESS"
    reason: str = ""
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert event record to dictionary format."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "timestamp_iso": self.timestamp_iso,
            "event_type": self.event_type,
            "machine_id": self.machine_id,
            "job_id": self.job_id,
            "technician_id": self.technician_id,
            "outcome": self.outcome,
            "reason": self.reason,
            "before_state": copy.deepcopy(self.before_state) if self.before_state is not None else None,
            "after_state": copy.deepcopy(self.after_state) if self.after_state is not None else None,
            "metadata": dict(self.metadata),
        }


class SimulationManager:
    """In-memory thread-safe state store and pull-based event logger for ForgeGuard simulation."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._event_seq: int = 0
        self._events: list[SimulationEvent] = []
        self._simulation_time: float = time.time()
        self._machines: dict[str, dict[str, Any]] = {}
        self._technicians: dict[str, dict[str, Any]] = {}
        self._active_jobs: dict[str, dict[str, Any]] = {}
        self._reschedule_queue: list[dict[str, Any]] = []
        self._recent_alerts: list[dict[str, Any]] = []

    def record_event(
        self,
        event_type: str,
        *,
        machine_id: Any = None,
        job_id: Any = None,
        technician_id: Any = None,
        outcome: str = "SUCCESS",
        reason: str = "",
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        event_time: float | None = None,
    ) -> SimulationEvent:
        """Appends an event record to the pull-based log."""
        with self._lock:
            self._event_seq += 1
            now = event_time if event_time is not None else time.time()
            self._simulation_time = now
            iso_str = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()

            ev = SimulationEvent(
                event_id=self._event_seq,
                timestamp=now,
                timestamp_iso=iso_str,
                event_type=str(event_type),
                machine_id=str(machine_id) if machine_id is not None else None,
                job_id=str(job_id) if job_id is not None else None,
                technician_id=str(technician_id) if technician_id is not None else None,
                outcome=str(outcome),
                reason=str(reason),
                before_state=copy.deepcopy(before_state) if before_state is not None else None,
                after_state=copy.deepcopy(after_state) if after_state is not None else None,
                metadata=dict(metadata or {}),
            )
            self._events.append(ev)
            return ev

    def get_events(self, since: int = 0, limit: int | None = None) -> list[dict[str, Any]]:
        """Returns events with event_id > since in ascending sequence order."""
        with self._lock:
            filtered = [ev.to_dict() for ev in self._events if ev.event_id > since]
            if limit is not None and limit > 0:
                filtered = filtered[:limit]
            return filtered

    def get_state(self) -> dict[str, Any]:
        """Returns complete snapshot of current simulation state."""
        with self._lock:
            now = self._simulation_time
            iso_str = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
            return {
                "simulation_time": now,
                "simulation_time_iso": iso_str,
                "fleet_status": {
                    "total_machines": len(self._machines),
                    "machines": copy.deepcopy(self._machines),
                },
                "technician_fleet": {
                    "total_technicians": len(self._technicians),
                    "technicians": copy.deepcopy(self._technicians),
                },
                "active_jobs": copy.deepcopy(self._active_jobs),
                "reschedule_queue": copy.deepcopy(self._reschedule_queue),
                "recent_alerts": copy.deepcopy(self._recent_alerts[-20:]),
                "total_events_recorded": len(self._events),
                "latest_event_id": self._event_seq,
            }

    def update_machine_reading(
        self,
        machine_id: str,
        reading: Mapping[str, Any],
        prediction: Mapping[str, Any] | None = None,
    ) -> None:
        """Updates live machine state with latest sensor reading and prediction."""
        with self._lock:
            mid = str(machine_id)
            if mid not in self._machines:
                self._machines[mid] = {
                    "machine_id": mid,
                    "status": "OPERATIONAL",
                    "telemetry": {},
                    "last_updated": time.time(),
                }
            self._machines[mid]["telemetry"] = dict(reading)
            self._machines[mid]["last_updated"] = time.time()
            if prediction is not None:
                self._machines[mid]["latest_prediction"] = dict(prediction)
                prob = prediction.get("failure_probability")
                if prob is not None and float(prob) >= 0.50:
                    self._machines[mid]["status"] = "ALERT"

    def register_technician(
        self,
        technician_id: str,
        name: str | None = None,
        shift_id: str | None = None,
    ) -> None:
        """Registers a technician in the simulation state."""
        with self._lock:
            tid = str(technician_id)
            if tid not in self._technicians:
                self._technicians[tid] = {
                    "technician_id": tid,
                    "name": name or f"Technician-{tid}",
                    "shift_id": shift_id or "SHIFT-1",
                    "active_job_id": None,
                    "interrupted_jobs": [],
                }

    def update_assignment(
        self,
        technician_id: str,
        job_id: str | None,
        interrupted_job_id: str | None = None,
    ) -> None:
        """Updates active assignment for a technician in simulation state."""
        with self._lock:
            tid = str(technician_id)
            if tid not in self._technicians:
                self.register_technician(tid)
            self._technicians[tid]["active_job_id"] = str(job_id) if job_id is not None else None
            if interrupted_job_id is not None:
                self._technicians[tid]["interrupted_jobs"].append(str(interrupted_job_id))

    def update_job(self, job_dict: Mapping[str, Any]) -> None:
        """Upserts an active or queued job in simulation state."""
        with self._lock:
            jid = str(job_dict.get("job_id", "UNKNOWN"))
            status = job_dict.get("status")
            job_copy = dict(job_dict)

            if status in ("interrupted", "paused"):
                # Put in reschedule queue if not present
                self._active_jobs.pop(jid, None)
                existing_idx = next((i for i, j in enumerate(self._reschedule_queue) if str(j.get("job_id")) == jid), None)
                if existing_idx is not None:
                    self._reschedule_queue[existing_idx] = job_copy
                else:
                    self._reschedule_queue.append(job_copy)
            elif status in ("in_progress", "active", "dispatched"):
                self._active_jobs[jid] = job_copy
                # Remove from reschedule queue if present
                self._reschedule_queue = [j for j in self._reschedule_queue if str(j.get("job_id")) != jid]
            elif status in ("completed", "canceled"):
                self._active_jobs.pop(jid, None)
                self._reschedule_queue = [j for j in self._reschedule_queue if str(j.get("job_id")) != jid]
            else:
                self._active_jobs[jid] = job_copy

    def reset(self) -> None:
        """Resets the simulation state and event log."""
        with self._lock:
            self._event_seq = 0
            self._events.clear()
            self._simulation_time = time.time()
            self._machines.clear()
            self._technicians.clear()
            self._active_jobs.clear()
            self._reschedule_queue.clear()
            self._recent_alerts.clear()


# Default singleton instance for simulation layer
default_simulation_manager = SimulationManager()


def get_simulation_state() -> dict[str, Any]:
    """Retrieve full live simulation state snapshot."""
    return default_simulation_manager.get_state()


def get_simulation_events(since: int = 0, limit: int | None = None) -> list[dict[str, Any]]:
    """Retrieve simulation event log records starting after cursor `since`."""
    return default_simulation_manager.get_events(since=since, limit=limit)


def record_simulation_event(
    event_type: str,
    *,
    machine_id: Any = None,
    job_id: Any = None,
    technician_id: Any = None,
    outcome: str = "SUCCESS",
    reason: str = "",
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> SimulationEvent:
    """Append an event to the default simulation event log."""
    return default_simulation_manager.record_event(
        event_type=event_type,
        machine_id=machine_id,
        job_id=job_id,
        technician_id=technician_id,
        outcome=outcome,
        reason=reason,
        before_state=before_state,
        after_state=after_state,
        metadata=metadata,
    )


def reset_simulation() -> None:
    """Reset the default simulation state and event log."""
    default_simulation_manager.reset()
