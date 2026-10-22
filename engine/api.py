"""FastAPI HTTP API and callable service interfaces for ForgeGuard Decision Engine.

Exposes stable, documented endpoints for the live simulation/orchestration layer and frontend:
1. POST /predict                     - Single-machine failure prediction
2. POST /predict/batch               - Batch/shift machine predictions
3. POST /decision/evaluate           - Cost-based operational alert decision
4. GET/POST /decision/threshold      - Threshold optimization result & cost curve
5. POST /schedule/plan               - Shift capacity allocation & priority dispatch
6. POST /safety/assess               - Equipment safety assessment (hard gate)
7. POST /schedule/preemption/evaluate- Pure preemption evaluation (no side-effects)
8. POST /schedule/preemption/execute - Preemption execution with safety re-check & idempotency
9. GET /simulation/state             - Live simulation fleet & technician state
10. GET /simulation/events           - Pull-based simulation event log (?since=<cursor>)
11. POST /simulation/reset           - Reset simulation state & event log
"""

from __future__ import annotations

import copy
import math
import time
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from engine.cost_model import CostConfig, calculate_cost, validate_cost_config
from engine.prediction_service import (
    predict_batch_machines,
    predict_single_machine,
    set_active_predict_fn,
)
from engine.preemption import (
    ALERT_CATEGORY_ACTUAL_FAILURE,
    ALERT_CATEGORY_CRITICAL_ALERT,
    ALERT_CATEGORY_PREDICTED_HIGH_RISK,
    ALERT_CATEGORY_ROUTINE,
    DEFAULT_PREEMPTION_CONFIG,
    JOB_STATUS_ACTIVE,
    JOB_STATUS_DISPATCHED,
    JOB_STATUS_IN_PROGRESS,
    JOB_STATUS_INTERRUPTED,
    JOB_STATUS_PAUSED,
    JOB_STATUS_PENDING,
    STATUS_DENIED,
    STATUS_EXECUTED,
    STATUS_NO_PREEMPTION,
    STATUS_PENDING_APPROVAL,
    MaintenanceJob,
    PreemptionConfig,
    PreemptionManager,
    PreemptionResult,
    evaluate_preemption,
    execute_preemption,
)
from engine.safety_assessment import (
    DEFAULT_EQUIPMENT_SAFETY_CONFIG,
    OUTCOME_INDETERMINATE,
    OUTCOME_SAFE_TO_INTERRUPT,
    OUTCOME_UNSAFE_TO_INTERRUPT,
    EquipmentSafetyConfig,
    MachineTelemetryContext,
    SafetyAssessmentResult,
    assess_job_safety,
)
from engine.scheduler import ScheduleResult, plan_shift
from engine.simulation import (
    default_simulation_manager,
    get_simulation_events,
    get_simulation_state,
    record_simulation_event,
    reset_simulation,
)
from engine.threshold import DEFAULT_THRESHOLD_GRID, ThresholdResult, choose_threshold

# ==============================================================================
# Cached Threshold Optimization State
# ==============================================================================

_CACHED_THRESHOLD_DATA: dict[str, Any] | None = None


def _init_cached_threshold_result(force: bool = False) -> dict[str, Any]:
    """Computes and caches default threshold optimization baseline at startup."""
    global _CACHED_THRESHOLD_DATA
    if _CACHED_THRESHOLD_DATA is not None and not force:
        return _CACHED_THRESHOLD_DATA

    # Deterministic standard validation baseline
    rng = np.random.RandomState(42)
    n_samples = 120
    y_true = rng.binomial(n=1, p=0.30, size=n_samples)
    probabilities = np.clip(
        np.where(y_true == 1, rng.beta(5, 2, size=n_samples), rng.beta(2, 5, size=n_samples)),
        0.02,
        0.98,
    )
    cost_cfg = CostConfig(false_negative_cost=20.0, false_positive_cost=1.0)
    res = choose_threshold(y_true=y_true, probabilities=probabilities, costs=cost_cfg)

    # Format threshold cost curve for plotting
    curve_data: list[dict[str, Any]] = []
    for _, row in res.cost_curve.iterrows():
        curve_data.append({
            "threshold": float(row["threshold"]),
            "total_cost": float(row["total_cost"]),
            "fn_cost": float(row["fn_cost"]),
            "fp_cost": float(row["fp_cost"]),
            "tp": int(row["tp"]),
            "tn": int(row["tn"]),
            "fp": int(row["fp"]),
            "fn": int(row["fn"]),
        })

    _CACHED_THRESHOLD_DATA = {
        "optimal_threshold": float(res.threshold),
        "optimal_cost": float(res.min_cost),
        "threshold_curve": curve_data,
        "confusion_matrix": dict(res.confusion_matrix),
        "baseline_comparison": {
            "baseline_threshold": float(res.baseline_threshold),
            "baseline_cost": float(res.baseline_cost),
            "cost_difference": float(res.cost_difference),
            "cost_reduction_pct": float(res.cost_reduction_pct),
            "is_optimal_better_or_equal": bool(res.is_optimal_better_or_equal),
            "baseline_confusion_matrix": dict(res.baseline_confusion_matrix),
        },
        "cost_config": cost_cfg.to_dict(),
        "metadata": {
            "cached": True,
            "sample_size": n_samples,
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
            "model_version": "ForgeGuard-Baseline-v1.0",
        },
        "explanation": res.explanation,
    }
    return _CACHED_THRESHOLD_DATA


# Initialize cache at module load
_init_cached_threshold_result()


# ==============================================================================
# Helper Function Implementations (Callable Python API)
# ==============================================================================

def evaluate_alert_decision(
    machine_id: Any,
    failure_probability: float,
    threshold: float | None = None,
    costs: CostConfig | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculates operational alert decision and cost breakdown for a failure probability."""
    if isinstance(failure_probability, bool) or not isinstance(failure_probability, (int, float, np.number)):
        raise TypeError(f"failure_probability must be numeric, got {type(failure_probability).__name__}.")
    prob = float(failure_probability)
    if not math.isfinite(prob) or not (0.0 <= prob <= 1.0):
        raise ValueError(f"failure_probability must be bounded within [0.0, 1.0], got {prob}.")

    cost_cfg = validate_cost_config(costs)

    if threshold is None:
        cached = _init_cached_threshold_result()
        selected_threshold = float(cached["optimal_threshold"])
    else:
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float, np.number)):
            raise TypeError(f"threshold must be numeric, got {type(threshold).__name__}.")
        selected_threshold = float(threshold)
        if not math.isfinite(selected_threshold) or not (0.0 <= selected_threshold <= 1.0):
            raise ValueError(f"threshold must be in [0.0, 1.0], got {selected_threshold}.")

    is_alert = prob >= selected_threshold
    priority_score = prob * cost_cfg.false_negative_cost

    # Operational penalties
    expected_fn_cost = prob * cost_cfg.false_negative_cost
    expected_fp_cost = (1.0 - prob) * cost_cfg.false_positive_cost

    reason_codes = (
        ["PROBABILITY_EXCEEDS_THRESHOLD", "ALERT_TRIGGERED"]
        if is_alert
        else ["PROBABILITY_BELOW_THRESHOLD", "NO_ALERT"]
    )

    explanation = (
        f"Failure probability {prob:.4f} >= threshold {selected_threshold:.2f}; "
        f"operational alert triggered with priority score {priority_score:.2f}."
        if is_alert
        else f"Failure probability {prob:.4f} < threshold {selected_threshold:.2f}; no operational alert triggered."
    )

    return {
        "machine_id": str(machine_id),
        "operational_alert": is_alert,
        "alert": is_alert,
        "threshold_used": selected_threshold,
        "config_identifier": f"CostConfig(fn={cost_cfg.false_negative_cost}, fp={cost_cfg.false_positive_cost})",
        "priority_score": round(priority_score, 4),
        "cost_breakdown": {
            "expected_fn_cost": round(expected_fn_cost, 4),
            "expected_fp_cost": round(expected_fp_cost, 4),
            "false_negative_unit_cost": float(cost_cfg.false_negative_cost),
            "false_positive_unit_cost": float(cost_cfg.false_positive_cost),
        },
        "reason_codes": reason_codes,
        "explanation": explanation,
    }


def get_threshold_optimization_result(
    y_val: Sequence[int | float | bool] | None = None,
    p_val: Sequence[float] | None = None,
    costs: CostConfig | Mapping[str, Any] | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Retrieves or recomputes optimal threshold, confusion matrix, and cost curve."""
    global _CACHED_THRESHOLD_DATA

    # If new validation data is supplied, recompute
    if y_val is not None and p_val is not None:
        cost_cfg = validate_cost_config(costs)
        res = choose_threshold(y_true=y_val, probabilities=p_val, costs=cost_cfg)
        curve_data: list[dict[str, Any]] = []
        for _, row in res.cost_curve.iterrows():
            curve_data.append({
                "threshold": float(row["threshold"]),
                "total_cost": float(row["total_cost"]),
                "fn_cost": float(row["fn_cost"]),
                "fp_cost": float(row["fp_cost"]),
                "tp": int(row["tp"]),
                "tn": int(row["tn"]),
                "fp": int(row["fp"]),
                "fn": int(row["fn"]),
            })

        recomputed = {
            "optimal_threshold": float(res.threshold),
            "optimal_cost": float(res.min_cost),
            "threshold_curve": curve_data,
            "confusion_matrix": dict(res.confusion_matrix),
            "baseline_comparison": {
                "baseline_threshold": float(res.baseline_threshold),
                "baseline_cost": float(res.baseline_cost),
                "cost_difference": float(res.cost_difference),
                "cost_reduction_pct": float(res.cost_reduction_pct),
                "is_optimal_better_or_equal": bool(res.is_optimal_better_or_equal),
                "baseline_confusion_matrix": dict(res.baseline_confusion_matrix),
            },
            "cost_config": cost_cfg.to_dict(),
            "metadata": {
                "cached": False,
                "sample_size": len(y_val),
                "refreshed_at": datetime.now(timezone.utc).isoformat(),
                "model_version": "ForgeGuard-Evaluated-v1.0",
            },
            "explanation": res.explanation,
        }
        if refresh:
            _CACHED_THRESHOLD_DATA = recomputed
        return recomputed

    if refresh:
        return _init_cached_threshold_result(force=True)

    return _init_cached_threshold_result()


def plan_shift_schedule(
    machines: Sequence[Mapping[str, Any]],
    slots: int = 3,
    threshold: float | None = None,
    costs: CostConfig | Mapping[str, Any] | None = None,
    id_column: str | None = None,
) -> dict[str, Any]:
    """Dispatches technician slots to high-priority alerted machines via plan_shift."""
    if not isinstance(machines, (list, tuple)):
        raise TypeError(f"machines must be a list of machine records, got {type(machines).__name__}.")
    if len(machines) == 0:
        raise ValueError("machines list cannot be empty.")

    if isinstance(slots, bool) or not isinstance(slots, (int, np.integer)):
        raise TypeError(f"slots must be an integer, got {type(slots).__name__}.")
    if slots < 0:
        raise ValueError(f"slots must be non-negative, got {slots}.")

    cost_cfg = validate_cost_config(costs)

    if threshold is None:
        cached = _init_cached_threshold_result()
        thresh = float(cached["optimal_threshold"])
    else:
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float, np.number)):
            raise TypeError(f"threshold must be numeric, got {type(threshold).__name__}.")
        thresh = float(threshold)
        if not math.isfinite(thresh) or not (0.0 <= thresh <= 1.0):
            raise ValueError(f"threshold must be in [0.0, 1.0], got {thresh}.")

    df = pd.DataFrame(list(machines))
    # Check for probability column
    prob_col = None
    for cand in ("failure_probability", "probability", "p_failure"):
        if cand in df.columns:
            prob_col = cand
            break

    if prob_col is None:
        raise ValueError("Machine records must contain 'failure_probability' column.")

    res: ScheduleResult = plan_shift(
        df=df,
        probabilities=df[prob_col],
        slots=int(slots),
        threshold=thresh,
        costs=cost_cfg,
        id_column=id_column,
    )

    sched_records = res.schedule_table.to_dict(orient="records")

    return {
        "selected_machines": list(res.selected_machines),
        "deferred_machines": list(res.deferred_machines),
        "unalerted_machines": list(res.unalerted_machines),
        "schedule_table": sched_records,
        "capacity_summary": {
            "slots": int(slots),
            "total_machines": len(df),
            "selected_count": len(res.selected_machines),
            "deferred_count": len(res.deferred_machines),
            "unalerted_count": len(res.unalerted_machines),
            "capacity_utilized": len(res.selected_machines),
            "capacity_remaining": max(0, int(slots) - len(res.selected_machines)),
        },
        "selection_reasons": dict(res.selection_reasons),
        "priority_formula": "priority_score = failure_probability * false_negative_cost (tie-broken by machine_id ascending alphanumeric)",
    }


def assess_safety(
    context: Mapping[str, Any] | MachineTelemetryContext,
    safety_config: Mapping[str, Any] | EquipmentSafetyConfig | None = None,
) -> dict[str, Any]:
    """Evaluates telemetry freshness, conflict, and safety rules for job interruptibility."""
    if isinstance(context, Mapping):
        ctx = MachineTelemetryContext.from_dict(context)
    elif isinstance(context, MachineTelemetryContext):
        ctx = context
    else:
        raise TypeError(f"context must be a mapping or MachineTelemetryContext, got {type(context).__name__}.")

    cfg: EquipmentSafetyConfig | None = None
    if safety_config is not None:
        if isinstance(safety_config, Mapping):
            cfg = EquipmentSafetyConfig.from_dict(safety_config)
        elif isinstance(safety_config, EquipmentSafetyConfig):
            cfg = safety_config
        else:
            raise TypeError(f"safety_config must be EquipmentSafetyConfig or mapping, got {type(safety_config).__name__}.")

    res: SafetyAssessmentResult = assess_job_safety(ctx, cfg)

    # Determine recommended operational procedure
    if res.outcome == OUTCOME_SAFE_TO_INTERRUPT:
        next_step = "PROCEED_WITH_SAFE_INTERRUPTION"
    elif res.outcome == OUTCOME_UNSAFE_TO_INTERRUPT:
        next_step = "TRIGGER_SAFE_STOP_PROCEDURE"
    else:
        next_step = "MANDATORY_SUPERVISOR_SAFETY_REVIEW"

    return {
        "outcome": res.outcome,
        "is_safe_to_interrupt": res.is_safe_to_interrupt,
        "evidence_used": dict(res.evidence_used),
        "missing_inputs": list(res.missing_inputs),
        "stale_signals": list(res.stale_signals),
        "conflicting_signals": dict(res.conflicting_signals),
        "evaluated_rules": list(res.evaluated_rules),
        "violated_rules": list(res.violated_rules),
        "uncertainty_factors": list(res.uncertainty_factors),
        "explanation": res.explanation,
        "required_next_step": next_step,
    }


def evaluate_preemption_request(
    current_job: Any,
    incoming_job: Any,
    technician_id: str | None = None,
    config: Mapping[str, Any] | PreemptionConfig | None = None,
    approved: bool = False,
) -> dict[str, Any]:
    """Pure preemption evaluation without mutating job states or technician assignments."""
    cfg: PreemptionConfig | None = None
    if config is not None:
        cfg = PreemptionConfig.from_dict(config) if isinstance(config, Mapping) else config

    res: PreemptionResult = evaluate_preemption(
        current_job,
        incoming_job,
        technician_id=technician_id,
        config=cfg,
        approved=approved,
    )
    return res.to_dict()


def execute_preemption_request(
    current_job: Any,
    incoming_job: Any,
    technician_id: str | None = None,
    config: Mapping[str, Any] | PreemptionConfig | None = None,
    approved: bool = False,
    timestamp: Any = None,
) -> dict[str, Any]:
    """Executes preemption with safety re-verification and idempotency."""
    cfg: PreemptionConfig | None = None
    if config is not None:
        cfg = PreemptionConfig.from_dict(config) if isinstance(config, Mapping) else config

    # Convert to MaintenanceJob instances
    from engine.preemption import _coerce_to_job
    cur = _coerce_to_job(current_job, "CUR")
    inc = _coerce_to_job(incoming_job, "INC")

    tech_id = technician_id or cur.technician_id or "TECH-01"

    # Idempotency check: if current job is ALREADY interrupted by this incoming job, return safe idempotent response
    if cur.status in (JOB_STATUS_INTERRUPTED, JOB_STATUS_PAUSED) and str(cur.preempted_by_job_id) == str(inc.job_id):
        return {
            "result": {
                "status": STATUS_EXECUTED,
                "preemption_executed": True,
                "requires_human_approval": False,
                "technician_id": tech_id,
                "interrupted_job_id": cur.job_id,
                "incoming_job_id": inc.job_id,
                "current_priority_score": cur.priority_score,
                "incoming_priority_score": inc.priority_score,
                "decision_reason": f"Preemption previously executed for job '{cur.job_id}' (idempotent request).",
                "interrupted_job_status": cur.status,
                "recommended_action": "Maintain current preemption assignment.",
                "safety_assessment": None,
            },
            "interrupted_job": cur.to_dict(),
            "incoming_job": inc.to_dict(),
            "assignment_state": {
                "technician_id": tech_id,
                "active_job_id": str(inc.job_id),
                "interrupted_jobs": [str(cur.job_id)],
            },
            "reschedule_queue": [cur.to_dict()],
        }

    # Re-evaluate immediately before execution
    res, updated_cur, updated_inc = execute_preemption(
        cur,
        inc,
        technician_id=tech_id,
        config=cfg,
        approved=approved,
        timestamp=timestamp,
    )

    if res.preemption_executed:
        # Update simulation state
        default_simulation_manager.update_assignment(
            technician_id=tech_id,
            job_id=str(updated_inc.job_id),
            interrupted_job_id=str(updated_cur.job_id),
        )
        default_simulation_manager.update_job(updated_cur.to_dict())
        default_simulation_manager.update_job(updated_inc.to_dict())
        record_simulation_event(
            event_type="PREEMPTION_EXECUTED",
            machine_id=updated_inc.machine_id,
            job_id=updated_inc.job_id,
            technician_id=tech_id,
            outcome="EXECUTED",
            reason=res.decision_reason,
            before_state={"active_job_id": str(cur.job_id), "status": cur.status},
            after_state={"active_job_id": str(updated_inc.job_id), "status": updated_inc.status},
        )
    else:
        record_simulation_event(
            event_type="PREEMPTION_DENIED",
            machine_id=inc.machine_id,
            job_id=inc.job_id,
            technician_id=tech_id,
            outcome=res.status.upper(),
            reason=res.decision_reason,
        )

    resched = [j for j in default_simulation_manager.get_state()["reschedule_queue"]]
    # Ensure current job is present in returned reschedule queue if preemption executed
    if res.preemption_executed and not any(j["job_id"] == updated_cur.job_id for j in resched):
        resched.append(updated_cur.to_dict())

    return {
        "result": res.to_dict(),
        "interrupted_job": updated_cur.to_dict(),
        "incoming_job": updated_inc.to_dict(),
        "assignment_state": {
            "technician_id": tech_id,
            "active_job_id": str(updated_inc.job_id) if res.preemption_executed else str(cur.job_id),
            "interrupted_jobs": [str(updated_cur.job_id)] if res.preemption_executed else [],
        },
        "reschedule_queue": resched,
    }


# ==============================================================================
# FastAPI Application & REST Endpoints
# ==============================================================================

app = FastAPI(
    title="ForgeGuard Decision Engine API",
    description="Cost-aware predictive maintenance and technician scheduling API for live simulation.",
    version="1.0.0",
)


# Standard Error Handler
def make_error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """Builds a consistent error JSON response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    msg = errors[0].get("msg", "Validation error") if errors else "Invalid request payload."
    field_loc = " -> ".join(str(l) for l in errors[0].get("loc", [])) if errors else ""
    return make_error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="INVALID_INPUT",
        message=f"{msg} ({field_loc})" if field_loc else msg,
        details={"validation_errors": errors},
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return make_error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="INVALID_INPUT",
        message=str(exc),
    )


@app.exception_handler(TypeError)
async def type_error_handler(request: Request, exc: TypeError) -> JSONResponse:
    return make_error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="INVALID_INPUT",
        message=str(exc),
    )


@app.exception_handler(KeyError)
async def key_error_handler(request: Request, exc: KeyError) -> JSONResponse:
    return make_error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        code="NOT_FOUND",
        message=str(exc).strip("'"),
    )


@app.exception_handler(ImportError)
async def import_error_handler(request: Request, exc: ImportError) -> JSONResponse:
    return make_error_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="MODEL_UNAVAILABLE",
        message=str(exc),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = "HTTP_ERROR"
    if exc.status_code == 400:
        code = "INVALID_INPUT"
    elif exc.status_code == 404:
        code = "NOT_FOUND"
    elif exc.status_code == 422:
        code = "UNPROCESSABLE_ENTITY"
    return make_error_response(
        status_code=exc.status_code,
        code=code,
        message=str(exc.detail),
    )


# ==============================================================================
# Endpoint Routes
# ==============================================================================

@app.get("/health")
def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "ForgeGuard Decision Engine"}


@app.post("/predict")
async def api_predict_single(request: Request) -> dict[str, Any]:
    """Single-machine failure prediction endpoint."""
    payload = await request.json()
    if not isinstance(payload, Mapping):
        raise ValueError("Request body must be a JSON object.")
    pred = predict_single_machine(payload)
    record_simulation_event(
        event_type="PREDICTION",
        machine_id=pred["machine_id"],
        outcome="PREDICTED",
        reason=f"Failure probability: {pred['failure_probability']:.4f}, mode: {pred['predicted_failure_mode']}",
        metadata=pred,
    )
    return pred


@app.post("/predict/batch")
async def api_predict_batch(request: Request) -> Any:
    """Batch/shift machine predictions endpoint."""
    payload = await request.json()
    if isinstance(payload, Mapping):
        readings = payload.get("machines", payload.get("readings"))
        if readings is None:
            raise ValueError("JSON object must contain 'machines' or 'readings' list.")
    elif isinstance(payload, list):
        readings = payload
    else:
        raise TypeError("Request body must be a JSON array or object with 'machines' list.")

    preds = predict_batch_machines(readings)
    record_simulation_event(
        event_type="PREDICTION_BATCH",
        outcome="PREDICTED",
        reason=f"Generated predictions for {len(preds)} fleet machines.",
        metadata={"machine_count": len(preds)},
    )
    return preds


@app.post("/decision/evaluate")
async def api_decision_evaluate(request: Request) -> dict[str, Any]:
    """Cost-based alert decision evaluation endpoint."""
    payload = await request.json()
    if not isinstance(payload, Mapping):
        raise ValueError("Request body must be a JSON object.")

    mid = payload.get("machine_id", payload.get("id", "M-UNKNOWN"))
    prob = payload.get("failure_probability", payload.get("probability"))
    if prob is None:
        raise ValueError("Missing required 'failure_probability' field.")

    thresh = payload.get("threshold")
    costs = payload.get("cost_config", payload.get("costs"))

    dec = evaluate_alert_decision(mid, prob, threshold=thresh, costs=costs)
    record_simulation_event(
        event_type="ALERT_EVALUATED",
        machine_id=mid,
        outcome="ALERT" if dec["operational_alert"] else "NO_ALERT",
        reason=dec["explanation"],
        metadata=dec,
    )
    return dec


@app.get("/decision/threshold")
def api_get_threshold() -> dict[str, Any]:
    """Returns optimal threshold, confusion matrix, baseline comparison, and cost curve."""
    return get_threshold_optimization_result()


@app.post("/decision/threshold")
async def api_post_threshold(request: Request) -> dict[str, Any]:
    """Recomputes or retrieves threshold optimization result."""
    body = await request.json() if (await request.body()) else {}
    y_val = body.get("y_val")
    p_val = body.get("p_val")
    costs = body.get("costs", body.get("cost_config"))
    refresh = bool(body.get("refresh", False))

    res = get_threshold_optimization_result(y_val=y_val, p_val=p_val, costs=costs, refresh=refresh)
    record_simulation_event(
        event_type="THRESHOLD_OPTIMIZED",
        outcome="OPTIMIZED",
        reason=f"Optimal threshold {res['optimal_threshold']:.2f} with min cost {res['optimal_cost']:.2f}.",
        metadata={"optimal_threshold": res["optimal_threshold"], "optimal_cost": res["optimal_cost"]},
    )
    return res


@app.post("/schedule/plan")
async def api_schedule_plan(request: Request) -> dict[str, Any]:
    """Plans shift maintenance schedule allocating technician slots by priority."""
    payload = await request.json()
    if not isinstance(payload, Mapping):
        raise ValueError("Request body must be a JSON object.")

    machines = payload.get("machines", payload.get("records"))
    if machines is None:
        raise ValueError("Missing required 'machines' list in payload.")

    slots = int(payload.get("slots", 3))
    threshold = payload.get("threshold")
    costs = payload.get("costs", payload.get("cost_config"))
    id_col = payload.get("id_column")

    plan = plan_shift_schedule(machines, slots=slots, threshold=threshold, costs=costs, id_column=id_col)
    record_simulation_event(
        event_type="SCHEDULE_PLANNED",
        outcome="PLANNED",
        reason=f"Dispatched {len(plan['selected_machines'])} machines across {slots} technician slots.",
        metadata={
            "selected_count": len(plan["selected_machines"]),
            "deferred_count": len(plan["deferred_machines"]),
            "unalerted_count": len(plan["unalerted_machines"]),
        },
    )
    return plan


@app.post("/safety/assess")
async def api_safety_assess(request: Request) -> dict[str, Any]:
    """Evaluates telemetry signals, freshness, and rules to determine job interruptibility."""
    payload = await request.json()
    if not isinstance(payload, Mapping):
        raise ValueError("Request body must be a JSON object.")

    # Context can be top-level or under 'context' key
    ctx_data = payload.get("context", payload)
    safety_cfg_data = payload.get("safety_config", payload.get("equipment_safety_config"))

    assessment = assess_safety(ctx_data, safety_config=safety_cfg_data)
    record_simulation_event(
        event_type="SAFETY_ASSESSED",
        machine_id=ctx_data.get("machine_id"),
        job_id=payload.get("active_job_id"),
        outcome=assessment["outcome"],
        reason=assessment["explanation"],
        metadata=assessment,
    )
    return assessment


@app.post("/schedule/preemption/evaluate")
async def api_preemption_evaluate(request: Request) -> dict[str, Any]:
    """Evaluates whether to preempt an active job without mutating assignments."""
    payload = await request.json()
    if not isinstance(payload, Mapping):
        raise ValueError("Request body must be a JSON object.")

    cur_job = payload.get("current_job")
    inc_job = payload.get("incoming_job")
    if cur_job is None or inc_job is None:
        raise ValueError("Both 'current_job' and 'incoming_job' are required.")

    tech_id = payload.get("technician_id")
    cfg = payload.get("config", payload.get("preemption_config"))
    approved = bool(payload.get("approved", False))

    res = evaluate_preemption_request(cur_job, inc_job, technician_id=tech_id, config=cfg, approved=approved)
    record_simulation_event(
        event_type="PREEMPTION_EVALUATED",
        job_id=inc_job.get("job_id") if isinstance(inc_job, Mapping) else None,
        technician_id=tech_id,
        outcome=res["status"].upper(),
        reason=res["decision_reason"],
        metadata=res,
    )
    return res


@app.post("/schedule/preemption/execute")
async def api_preemption_execute(request: Request) -> dict[str, Any]:
    """Executes preemption if permitted, mutating assignments with idempotency."""
    payload = await request.json()
    if not isinstance(payload, Mapping):
        raise ValueError("Request body must be a JSON object.")

    cur_job = payload.get("current_job")
    inc_job = payload.get("incoming_job")
    if cur_job is None or inc_job is None:
        raise ValueError("Both 'current_job' and 'incoming_job' are required.")

    tech_id = payload.get("technician_id")
    cfg = payload.get("config", payload.get("preemption_config"))
    approved = bool(payload.get("approved", False))
    ts = payload.get("timestamp")

    return execute_preemption_request(cur_job, inc_job, technician_id=tech_id, config=cfg, approved=approved, timestamp=ts)


@app.get("/simulation/state")
def api_simulation_state() -> dict[str, Any]:
    """Returns current live simulation fleet, technician assignments, and queues."""
    return get_simulation_state()


@app.get("/simulation/events")
def api_simulation_events(since: int = 0, limit: int | None = None) -> list[dict[str, Any]]:
    """Returns pull-based simulation event log starting after sequence cursor 'since'."""
    return get_simulation_events(since=since, limit=limit)


@app.post("/simulation/reset")
def api_simulation_reset() -> dict[str, str]:
    """Resets simulation state and event log."""
    reset_simulation()
    return {"status": "reset", "message": "Simulation state and event log have been cleared."}
