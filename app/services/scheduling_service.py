"""Scheduling service managing shift allocation and replanning."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.clients.engine_client import EngineClient, EngineConnectionError, EngineTimeoutError
from app.schemas.common import JobPriority, JobStatus
from app.schemas.schedule import ReplanRequest, ScheduleAssignment, ScheduleResponse
from app.services.state_service import StateService, get_state_service

logger = logging.getLogger(__name__)


class SchedulingService:
    """Coordinates shift schedule planning with the Decision Engine."""

    def __init__(self, engine_client: Optional[EngineClient] = None, state_service: Optional[StateService] = None):
        self.engine_client = engine_client or EngineClient()
        self.state_service = state_service or get_state_service()

    async def get_current_schedule(self) -> ScheduleResponse:
        """Returns the canonical active schedule."""
        return self.state_service.schedule

    async def replan_schedule(self, request: ReplanRequest) -> ScheduleResponse:
        """Executes Workflow C: Recompute schedule through Decision Engine.

        INVARIANT:
        If engine request fails or times out, the previous valid schedule is preserved.
        Assignments are never half-replaced.
        """
        old_schedule = self.state_service.schedule
        now = datetime.now(timezone.utc)

        # 1. Build machine alert list and technician capacity
        machine_alerts = []
        for m_id, m in self.state_service.machines.items():
            prob = m.failure_probability if m.failure_probability is not None else 0.0
            machine_alerts.append({
                "machine_id": m_id,
                "failure_probability": prob,
                "predicted_failure_mode": m.predicted_failure_mode,
            })

        slots_count = len(self.state_service.technicians)
        payload = {
            "machines": machine_alerts,
            "slots": slots_count,
            "reason": request.reason,
            "trigger_job_id": request.trigger_job_id,
        }

        try:
            # 2. Call Engine /schedule/plan
            engine_res = await self.engine_client.plan_schedule(payload)

            selected = engine_res.get("selected_machines", [])
            deferred = engine_res.get("deferred_machines", [])
            unalerted = engine_res.get("unalerted_machines", [])
            raw_assignments = engine_res.get("assignments") or engine_res.get("schedule_table") or []

            # 3. Reconcile assignments
            new_assignments: List[ScheduleAssignment] = []
            if isinstance(raw_assignments, list) and raw_assignments:
                for item in raw_assignments:
                    if isinstance(item, dict):
                        new_assignments.append(
                            ScheduleAssignment(
                                job_id=item.get("job_id") or f"JOB-PLAN-{item.get('machine_id', 'X')}",
                                machine_id=item.get("machine_id", "M-UNKNOWN"),
                                technician_id=item.get("technician_id"),
                                planned_start_at=now,
                                status=item.get("status", "planned"),
                                priority_score=item.get("priority_score"),
                                reason=item.get("reason") or item.get("selection_reason"),
                            )
                        )
            else:
                # Map selected machines to available technicians
                tech_ids = list(self.state_service.technicians.keys())
                for idx, m_id in enumerate(selected):
                    t_id = tech_ids[idx] if idx < len(tech_ids) else None
                    new_assignments.append(
                        ScheduleAssignment(
                            job_id=f"JOB-SCHED-{m_id}",
                            machine_id=m_id,
                            technician_id=t_id,
                            planned_start_at=now,
                            status="planned" if not t_id else "assigned",
                            priority_score=0.8 - (idx * 0.1),
                            reason=f"Selected by shift scheduler (priority rank #{idx + 1})",
                        )
                    )

            # 4. Atomic schedule update
            updated_schedule = ScheduleResponse(
                generated_at=now,
                assignments=new_assignments,
                selected_machines=selected,
                deferred_machines=deferred,
                unalerted_machines=unalerted,
                capacity_summary={
                    "total_slots": slots_count,
                    "allocated_slots": len(new_assignments),
                    "free_slots": max(0, slots_count - len(new_assignments)),
                },
            )
            self.state_service.schedule = updated_schedule

            # 5. Record schedule update event
            self.state_service.record_event(
                event_type="schedule_replanned",
                outcome="success",
                reason=f"Schedule replanned: {len(new_assignments)} assignments created",
                severity="info",
                details={
                    "trigger_reason": request.reason,
                    "selected_count": len(selected),
                    "deferred_count": len(deferred),
                },
            )

            return updated_schedule

        except (EngineConnectionError, EngineTimeoutError) as exc:
            logger.warning(f"Engine schedule replan failed ({exc}). Retaining previous schedule.")
            self.state_service.record_event(
                event_type="schedule_replan_failed",
                outcome="retained_previous",
                reason=f"Engine connection failed: {exc}. Retained previous valid schedule.",
                severity="warning",
                details={"error": str(exc)},
            )
            # Guarantee invariant: Keep old state available if replanning fails
            return old_schedule
