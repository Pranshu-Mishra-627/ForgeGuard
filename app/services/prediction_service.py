"""Prediction service coordinating ML inferences with Decision Engine."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.clients.engine_client import EngineClient, EngineConnectionError, EngineTimeoutError
from app.schemas.common import MachineDecision, MachineStatus
from app.schemas.machines import MachineResponse, TelemetryReading
from app.services.state_service import StateService, get_state_service

logger = logging.getLogger(__name__)


class PredictionService:
    """Coordinates prediction pipelines and machine telemetry updates."""

    def __init__(self, engine_client: Optional[EngineClient] = None, state_service: Optional[StateService] = None):
        self.engine_client = engine_client or EngineClient()
        self.state_service = state_service or get_state_service()

    async def predict_single(self, machine_id: str, reading: TelemetryReading) -> MachineResponse:
        """Executes Workflow A: Single-machine prediction & operational decision."""
        payload = {
            "machine_id": machine_id,
            "air_temperature": reading.air_temperature,
            "process_temperature": reading.process_temperature,
            "rotational_speed": reading.rotational_speed,
            "torque": reading.torque,
            "tool_wear": reading.tool_wear,
            "type": reading.machine_type,
        }

        # 1. Call Engine /predict
        pred_res = await self.engine_client.predict(payload)

        # 2. Extract normalized outputs
        failure_prob = pred_res.get("failure_probability", 0.0)
        failure_mode = pred_res.get("predicted_failure_mode")

        # 3. Call Engine /decision/evaluate
        decision_val = MachineDecision.MONITOR
        try:
            decision_res = await self.engine_client.evaluate_decision({
                "machine_id": machine_id,
                "failure_probability": failure_prob,
                "predicted_failure_mode": failure_mode,
            })
            raw_decision = decision_res.get("alert_decision") or decision_res.get("decision", "monitor")
            if raw_decision in [d.value for d in MachineDecision]:
                decision_val = MachineDecision(raw_decision)
        except (EngineConnectionError, EngineTimeoutError) as exc:
            logger.warning(f"Engine decision service unreachable during predict_single: {exc}")
            # Retain existing decision or fallback without faking engine formulas
            decision_val = MachineDecision.UNKNOWN

        # 4. Update canonical state
        now = datetime.now(timezone.utc)
        machine_status = MachineStatus.HEALTHY
        if failure_prob >= 0.7:
            machine_status = MachineStatus.CRITICAL
        elif failure_prob >= 0.2:
            machine_status = MachineStatus.WATCH

        current_machine = self.state_service.machines.get(machine_id)
        name = current_machine.name if current_machine else f"Machine {machine_id}"
        active_job = current_machine.active_job_id if current_machine else None

        updated_machine = MachineResponse(
            machine_id=machine_id,
            name=name,
            status=machine_status,
            failure_probability=failure_prob,
            predicted_failure_mode=failure_mode,
            last_telemetry_at=now,
            decision=decision_val,
            remaining_useful_life_hours=None,  # Do not invent RUL if unsupported
            safety_status=current_machine.safety_status if current_machine else MachineStatus.UNKNOWN,
            active_job_id=active_job,
            telemetry=payload,
        )

        self.state_service.machines[machine_id] = updated_machine

        # 5. Record confirmed audit event
        self.state_service.record_event(
            event_type="prediction_recorded",
            machine_id=machine_id,
            outcome="success",
            reason=f"Predicted failure probability: {failure_prob:.3f}",
            severity="warning" if failure_prob >= 0.5 else "info",
            details={
                "failure_probability": failure_prob,
                "predicted_failure_mode": failure_mode,
                "decision": decision_val.value,
            },
        )

        return updated_machine

    async def predict_batch(self, readings: List[Dict[str, Any]]) -> List[MachineResponse]:
        """Executes Workflow B: Batch prediction preserving machine identities."""
        # Call Engine /predict/batch
        batch_res = await self.engine_client.predict_batch(readings)

        # Batch response normalization
        predictions_list = []
        if isinstance(batch_res, list):
            predictions_list = batch_res
        elif isinstance(batch_res, dict):
            predictions_list = batch_res.get("predictions") or batch_res.get("results") or []

        results = []
        for pred in predictions_list:
            m_id = pred.get("machine_id")
            if not m_id:
                continue

            failure_prob = pred.get("failure_probability")
            failure_mode = pred.get("predicted_failure_mode")

            # Update state with preserved machine identity
            curr = self.state_service.machines.get(m_id)
            if curr:
                status = MachineStatus.HEALTHY
                if failure_prob is not None:
                    if failure_prob >= 0.7:
                        status = MachineStatus.CRITICAL
                    elif failure_prob >= 0.2:
                        status = MachineStatus.WATCH

                updated = curr.model_copy(
                    update={
                        "failure_probability": failure_prob,
                        "predicted_failure_mode": failure_mode,
                        "status": status,
                    }
                )
                self.state_service.machines[m_id] = updated
                results.append(updated)

        self.state_service.record_event(
            event_type="batch_prediction_completed",
            outcome="success",
            reason=f"Processed batch of {len(results)} machine readings",
            severity="info",
            details={"count": len(results)},
        )

        return results
