# ForgeGuard Decision Engine — Interface & API Reference

**Person 2: Decision Engine & Live Simulation Interfaces**  
**Version:** `1.0.0`  
**Test Suite Verification:** `238 passed in 3.70s` (205 existing + 33 new API tests)

---

## 1. Implementation Inventory

| Capability | Module & Function | Status | Description |
|---|---|---|---|
| **Single-Machine Prediction** | [`predict_single_machine()`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/prediction_service.py)<br>`POST /predict` | **Implemented** | Adapts Person 1's ML model or registered predictor, validates inputs, and returns failure probability, predicted failure mode, alert, and metadata. |
| **Batch/Shift Prediction** | [`predict_batch_machines()`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/prediction_service.py)<br>`POST /predict/batch` | **Implemented** | Batches fleet machine readings into an aligned DataFrame, validates numeric and identity fields, and preserves machine ordering. |
| **Cost-Based Alert Decision** | [`evaluate_alert_decision()`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/api.py)<br>`POST /decision/evaluate` | **Implemented** | Evaluates failure probability against operational threshold, calculates priority score ($p \times C_{\text{FN}}$), and exposes cost breakdown. |
| **Threshold Optimization** | [`get_threshold_optimization_result()`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/api.py)<br>`GET /decision/threshold`<br>`POST /decision/threshold` | **Implemented** | Exposes optimal threshold from [`choose_threshold()`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/threshold.py), full cost curve chart data, confusion matrix, and 0.50 baseline comparison. Cached at startup. |
| **Shift Planning** | [`plan_shift_schedule()`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/api.py)<br>`POST /schedule/plan` | **Implemented** | Invokes [`plan_shift()`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/scheduler.py) to rank alerted machines by priority score, select up to available technician slots, and defer remaining with clear explanations. |
| **Equipment Safety Assessment** | [`assess_safety()`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/api.py)<br>`POST /safety/assess` | **Implemented** | Hard gate evaluating telemetry freshness, sensor discrepancies, active hazards, and externalized rules via [`assess_job_safety()`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/safety_assessment.py). |
| **Preemption Evaluation** | [`evaluate_preemption_request()`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/api.py)<br>`POST /schedule/preemption/evaluate` | **Implemented** | Pure assessment of preemption criteria via [`evaluate_preemption()`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/preemption.py). Zero side effects or assignment mutations. |
| **Preemption Execution** | [`execute_preemption_request()`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/api.py)<br>`POST /schedule/preemption/execute` | **Implemented** | Re-verifies safety immediately before mutating state, safely pauses current job, preserves progress in reschedule queue, assigns incoming job, and ensures idempotency. |
| **Simulation State** | [`get_simulation_state()`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/simulation.py)<br>`GET /simulation/state` | **Implemented** | Provides snapshot of fleet health, technician assignments, active jobs, and reschedule queue. |
| **Simulation Event Log** | [`get_simulation_events()`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/simulation.py)<br>`GET /simulation/events?since=<cursor>` | **Implemented** | Pull-based event stream with monotonic event IDs, timestamps, before/after states, and filtering. |

---

## 2. API Error Contract

All HTTP endpoints adhere to a standardized error response structure:

```json
{
  "error": {
    "code": "INVALID_INPUT",
    "message": "Missing required machine identifier 'machine_id'.",
    "details": {}
  }
}
```

### Standard Error Codes

- `INVALID_INPUT` (HTTP 400): Missing required fields, non-finite numbers, negative slot capacity, or probabilities outside `[0.0, 1.0]`.
- `NOT_FOUND` (HTTP 404): Machine ID, job ID, or technician ID not found in schedule or fleet records.
- `UNPROCESSABLE_ENTITY` (HTTP 422): Malformed JSON or schema constraint violation.
- `MODEL_UNAVAILABLE` (HTTP 503): Person 1's ML prediction function is not installed and no pre-computed probabilities were provided.
- `INTERNAL_ERROR` (HTTP 500): Unexpected engine exception. Stack traces are masked from the client.

---

## 3. Endpoints & Schemas

### A. Single-Machine Prediction

- **Python Callable:** [`predict_single_machine(reading, predict_fn=None, model_version=None)`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/prediction_service.py)
- **HTTP Route:** `POST /predict`
- **Description:** Accepts a single machine reading or sensor dictionary and runs Person 1's ML prediction.

#### Request Schema
```json
{
  "machine_id": "CNC-001",
  "temperature_c": 74.2,
  "vibration_rms": 2.45,
  "factory_line": "Line-A"
}
```
*Required fields:* `machine_id` (or `id`).  
*Optional fields:* Numerical sensor readings (`temperature_c`, `vibration_rms`, etc.), `timestamp`, metadata.

#### Successful Response (HTTP 200)
```json
{
  "machine_id": "CNC-001",
  "failure_probability": 0.85,
  "predicted_failure_mode": "Bearing Wear",
  "maintenance_alert": true,
  "prediction_timestamp": "2026-10-22T08:50:00Z",
  "model_version": "ForgeGuard-ML-v1.0",
  "prediction_horizon": null
}
```

#### Failure Example (HTTP 400)
```json
// POST /predict with {"temperature_c": 75.0}
{
  "error": {
    "code": "INVALID_INPUT",
    "message": "Missing required machine identifier 'machine_id'.",
    "details": {}
  }
}
```

---

### B. Batch / Shift Prediction

- **Python Callable:** [`predict_batch_machines(readings, predict_fn=None, model_version=None)`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/prediction_service.py)
- **HTTP Route:** `POST /predict/batch`
- **Description:** Accepts a fleet of machine readings in a single payload and returns predictions aligned in input order.

#### Request Schema
```json
{
  "machines": [
    {"machine_id": "CNC-001", "temperature_c": 74.2, "vibration_rms": 2.45},
    {"machine_id": "CNC-002", "temperature_c": 88.5, "vibration_rms": 4.10},
    {"machine_id": "CNC-003", "temperature_c": 58.0, "vibration_rms": 1.20}
  ]
}
```
*Note:* The endpoint also accepts a raw JSON array `[ { ... }, { ... } ]`.

#### Successful Response (HTTP 200)
```json
[
  {
    "machine_id": "CNC-001",
    "failure_probability": 0.85,
    "predicted_failure_mode": "Bearing Wear",
    "maintenance_alert": true,
    "prediction_timestamp": "2026-10-22T08:50:00Z",
    "model_version": "ForgeGuard-ML-v1.0",
    "prediction_horizon": null
  },
  {
    "machine_id": "CNC-002",
    "failure_probability": 0.72,
    "predicted_failure_mode": "Overheating",
    "maintenance_alert": true,
    "prediction_timestamp": "2026-10-22T08:50:00Z",
    "model_version": "ForgeGuard-ML-v1.0",
    "prediction_horizon": null
  },
  {
    "machine_id": "CNC-003",
    "failure_probability": 0.15,
    "predicted_failure_mode": "None",
    "maintenance_alert": false,
    "prediction_timestamp": "2026-10-22T08:50:00Z",
    "model_version": "ForgeGuard-ML-v1.0",
    "prediction_horizon": null
  }
]
```

*Batch Failure Semantics:* Batch inputs are validated atomically. If any machine reading contains malformed or non-finite readings, HTTP 400 is returned detailing the offending record.

---

### C. Cost-Based Alert Decision

- **Python Callable:** [`evaluate_alert_decision(machine_id, failure_probability, threshold=None, costs=None)`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/api.py)
- **HTTP Route:** `POST /decision/evaluate`
- **Description:** Evaluates failure probability against operational threshold and calculates expected penalty components.

#### Request Schema
```json
{
  "machine_id": "CNC-001",
  "failure_probability": 0.85,
  "threshold": 0.50,
  "costs": {
    "false_negative_cost": 20.0,
    "false_positive_cost": 1.0
  }
}
```

#### Successful Response (HTTP 200)
```json
{
  "machine_id": "CNC-001",
  "operational_alert": true,
  "alert": true,
  "threshold_used": 0.5,
  "config_identifier": "CostConfig(fn=20.0, fp=1.0)",
  "priority_score": 17.0,
  "cost_breakdown": {
    "expected_fn_cost": 17.0,
    "expected_fp_cost": 0.15,
    "false_negative_unit_cost": 20.0,
    "false_positive_unit_cost": 1.0
  },
  "reason_codes": [
    "PROBABILITY_EXCEEDS_THRESHOLD",
    "ALERT_TRIGGERED"
  ],
  "explanation": "Failure probability 0.8500 >= threshold 0.50; operational alert triggered with priority score 17.00."
}
```

---

### D. Threshold Optimization Result

- **Python Callable:** [`get_threshold_optimization_result(y_val=None, p_val=None, costs=None, refresh=False)`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/api.py)
- **HTTP Routes:** `GET /decision/threshold` and `POST /decision/threshold`
- **Description:** Exposes optimal operational threshold minimizing validation penalty units, threshold-versus-cost curve, confusion matrix, and 0.50 baseline comparison.

#### Successful Response (HTTP 200)
```json
{
  "optimal_threshold": 0.42,
  "optimal_cost": 142.0,
  "threshold_curve": [
    {"threshold": 0.0, "total_cost": 240.0, "fn_cost": 0.0, "fp_cost": 240.0, "tp": 36, "tn": 0, "fp": 84, "fn": 0},
    {"threshold": 0.42, "total_cost": 142.0, "fn_cost": 80.0, "fp_cost": 62.0, "tp": 32, "tn": 72, "fp": 12, "fn": 4}
  ],
  "confusion_matrix": {
    "tp": 32,
    "tn": 72,
    "fp": 12,
    "fn": 4
  },
  "baseline_comparison": {
    "baseline_threshold": 0.5,
    "baseline_cost": 165.0,
    "cost_difference": 23.0,
    "cost_reduction_pct": 13.94,
    "is_optimal_better_or_equal": true,
    "baseline_confusion_matrix": {"tp": 28, "tn": 75, "fp": 9, "fn": 8}
  },
  "cost_config": {
    "false_negative_cost": 20.0,
    "false_positive_cost": 1.0
  },
  "metadata": {
    "cached": true,
    "sample_size": 120,
    "refreshed_at": "2026-10-22T08:50:00Z",
    "model_version": "ForgeGuard-Baseline-v1.0"
  },
  "explanation": "Explainable Threshold Cost Analysis: Optimal Operational Threshold 0.42 (Total Cost: 142.00) vs Baseline 0.50 (Total Cost: 165.00). Cost savings: 23.00 (13.9% reduction)."
}
```

---

### E. Shift Planning & Priority Dispatch

- **Python Callable:** [`plan_shift_schedule(machines, slots=3, threshold=None, costs=None)`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/api.py)
- **HTTP Route:** `POST /schedule/plan`
- **Description:** Allocates technician slots deterministically under capacity constraints using the priority formula:
  $$\text{priority\_score} = \text{failure\_probability} \times \text{false\_negative\_cost}$$
  Ties are broken deterministically by ascending alphanumeric machine ID (`M-001` before `M-002`).

#### Request Schema
```json
{
  "machines": [
    {"machine_id": "CNC-001", "failure_probability": 0.90},
    {"machine_id": "CNC-002", "failure_probability": 0.85},
    {"machine_id": "CNC-003", "failure_probability": 0.70},
    {"machine_id": "CNC-004", "failure_probability": 0.20}
  ],
  "slots": 2,
  "threshold": 0.50,
  "costs": {
    "false_negative_cost": 20.0,
    "false_positive_cost": 1.0
  }
}
```

#### Successful Response (HTTP 200)
```json
{
  "selected_machines": ["CNC-001", "CNC-002"],
  "deferred_machines": ["CNC-003"],
  "unalerted_machines": ["CNC-004"],
  "schedule_table": [
    {
      "machine_id": "CNC-001",
      "failure_probability": 0.9,
      "alert": true,
      "priority_score": 18.0,
      "selected_for_service": true,
      "reason": "Selected for service (Priority rank #1, score: 18.00)."
    },
    {
      "machine_id": "CNC-002",
      "failure_probability": 0.85,
      "alert": true,
      "priority_score": 17.0,
      "selected_for_service": true,
      "reason": "Selected for service (Priority rank #2, score: 17.00)."
    },
    {
      "machine_id": "CNC-003",
      "failure_probability": 0.7,
      "alert": true,
      "priority_score": 14.0,
      "selected_for_service": false,
      "reason": "Deferred: alert triggered (score: 14.00) but technician capacity (2 slots) exceeded."
    },
    {
      "machine_id": "CNC-004",
      "failure_probability": 0.2,
      "alert": false,
      "priority_score": 4.0,
      "selected_for_service": false,
      "reason": "Not alerted: failure probability (0.20) below threshold (0.50)."
    }
  ],
  "capacity_summary": {
    "slots": 2,
    "total_machines": 4,
    "selected_count": 2,
    "deferred_count": 1,
    "unalerted_count": 1,
    "capacity_utilized": 2,
    "capacity_remaining": 0
  },
  "selection_reasons": {
    "CNC-001": "Selected for service (Priority rank #1, score: 18.00).",
    "CNC-002": "Selected for service (Priority rank #2, score: 17.00).",
    "CNC-003": "Deferred: alert triggered (score: 14.00) but technician capacity (2 slots) exceeded.",
    "CNC-004": "Not alerted: failure probability (0.20) below threshold (0.50)."
  },
  "priority_formula": "priority_score = failure_probability * false_negative_cost (tie-broken by machine_id ascending alphanumeric)"
}
```

---

### F. Equipment Safety Assessment (Hard Gate)

- **Python Callable:** [`assess_safety(context, safety_config=None)`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/api.py)
- **HTTP Route:** `POST /safety/assess`
- **Description:** Evaluates whether an active machine job is safe to interrupt based on telemetry freshness, sensor discrepancies, active hazards, and externalized limits.
- **Safety Hard Gate:** An `UNSAFE_TO_INTERRUPT` or `INDETERMINATE` assessment CANNOT be bypassed by higher priority scores or urgency.

#### Request Schema
```json
{
  "active_job_id": "JOB-001",
  "machine_id": "CNC-001",
  "current_maintenance_stage": "inspection",
  "is_reversible_stage": true,
  "telemetry_signals": {
    "temperature_c": 68.5,
    "vibration_rms": 2.1
  },
  "redundant_signals": {
    "temperature_c": 70.0
  },
  "timestamp": 1729587000.0,
  "current_time": 1729587030.0,
  "active_hazards": []
}
```

#### Successful Response (Safe, HTTP 200)
```json
{
  "outcome": "SAFE_TO_INTERRUPT",
  "is_safe_to_interrupt": true,
  "evidence_used": {
    "temperature_c": 68.5,
    "vibration_rms": 2.1,
    "maintenance_stage": "inspection",
    "is_reversible_stage": true
  },
  "missing_inputs": [],
  "stale_signals": [],
  "conflicting_signals": {},
  "evaluated_rules": ["RULE_MAX_TEMPERATURE", "RULE_MAX_VIBRATION"],
  "violated_rules": [],
  "uncertainty_factors": [],
  "explanation": "Equipment signals are within configured safety thresholds. Job is verified safe to pause.",
  "required_next_step": "PROCEED_WITH_SAFE_INTERRUPTION"
}
```

#### Unsafe Response (Overheating, HTTP 200)
```json
{
  "outcome": "UNSAFE_TO_INTERRUPT",
  "is_safe_to_interrupt": false,
  "evidence_used": {"temperature_c": 92.5},
  "missing_inputs": [],
  "stale_signals": [],
  "conflicting_signals": {},
  "evaluated_rules": ["RULE_MAX_TEMPERATURE"],
  "violated_rules": ["RULE_MAX_TEMPERATURE"],
  "uncertainty_factors": [],
  "explanation": "Temperature 92.5°C exceeds maximum allowable operating threshold (85.0°C).",
  "required_next_step": "TRIGGER_SAFE_STOP_PROCEDURE"
}
```

---

### G. Preemption Evaluation

- **Python Callable:** [`evaluate_preemption_request(current_job, incoming_job, technician_id=None, config=None, approved=False)`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/api.py)
- **HTTP Route:** `POST /schedule/preemption/evaluate`
- **Description:** Pure evaluation of preemption eligibility. Does NOT mutate assignments or job states.

#### Request Schema
```json
{
  "current_job": {
    "job_id": "JOB-001",
    "machine_id": "CNC-001",
    "priority_score": 15.0,
    "status": "in_progress",
    "job_type": "preventive_maintenance",
    "is_interruptible": true,
    "technician_id": "TECH-01"
  },
  "incoming_job": {
    "job_id": "JOB-EMERGENCY",
    "machine_id": "PRESS-09",
    "priority_score": 95.0,
    "alert_category": "actual_failure"
  },
  "technician_id": "TECH-01",
  "approved": false
}
```

#### Successful Response (HTTP 200)
```json
{
  "status": "executed",
  "preemption_executed": false,
  "requires_human_approval": false,
  "technician_id": "TECH-01",
  "interrupted_job_id": "JOB-001",
  "incoming_job_id": "JOB-EMERGENCY",
  "current_priority_score": 15.0,
  "incoming_priority_score": 95.0,
  "decision_reason": "Preemption authorized: Actual machine breakdown failure (priority 95.00) exceeds current job 'JOB-001' (priority 15.00, delta 80.00). Current job is safely interruptible.",
  "interrupted_job_status": "in_progress",
  "recommended_action": "Safely pause current job, preserve progress state, and dispatch technician to incoming job.",
  "safety_assessment": null
}
```

---

### H. Preemption Execution

- **Python Callable:** [`execute_preemption_request(current_job, incoming_job, technician_id=None, config=None, approved=False, timestamp=None)`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/api.py)
- **HTTP Route:** `POST /schedule/preemption/execute`
- **Description:** Mutates assignments and job state only if permitted. Ensures work progress preservation, reschedule queue entry, and idempotency.

#### Request Schema
```json
{
  "current_job": {
    "job_id": "JOB-001",
    "machine_id": "CNC-001",
    "priority_score": 15.0,
    "status": "in_progress",
    "is_interruptible": true,
    "progress": {"completed_steps": 2, "percentage": 40.0},
    "started_at": 1729585000.0,
    "technician_id": "TECH-01"
  },
  "incoming_job": {
    "job_id": "JOB-EMERGENCY",
    "machine_id": "PRESS-09",
    "priority_score": 95.0,
    "alert_category": "actual_failure"
  },
  "technician_id": "TECH-01"
}
```

#### Successful Response (HTTP 200)
```json
{
  "result": {
    "status": "executed",
    "preemption_executed": true,
    "requires_human_approval": false,
    "technician_id": "TECH-01",
    "interrupted_job_id": "JOB-001",
    "incoming_job_id": "JOB-EMERGENCY",
    "current_priority_score": 15.0,
    "incoming_priority_score": 95.0,
    "decision_reason": "Preemption authorized: Actual machine breakdown failure (priority 95.00) exceeds current job 'JOB-001' (priority 15.00, delta 80.00). Current job is safely interruptible.",
    "interrupted_job_status": "interrupted",
    "recommended_action": "Safely pause current job, preserve progress state, and dispatch technician to incoming job.",
    "safety_assessment": null
  },
  "interrupted_job": {
    "job_id": "JOB-001",
    "machine_id": "CNC-001",
    "status": "interrupted",
    "progress": {"completed_steps": 2, "percentage": 40.0},
    "started_at": 1729585000.0,
    "preempted_by_job_id": "JOB-EMERGENCY",
    "interruption_reason": "Preemption authorized: Actual machine breakdown failure (priority 95.00) exceeds current job 'JOB-001' (priority 15.00, delta 80.00). Current job is safely interruptible."
  },
  "incoming_job": {
    "job_id": "JOB-EMERGENCY",
    "machine_id": "PRESS-09",
    "status": "in_progress",
    "technician_id": "TECH-01"
  },
  "assignment_state": {
    "technician_id": "TECH-01",
    "active_job_id": "JOB-EMERGENCY",
    "interrupted_jobs": ["JOB-001"]
  },
  "reschedule_queue": [
    {
      "job_id": "JOB-001",
      "machine_id": "CNC-001",
      "status": "interrupted"
    }
  ]
}
```

*Idempotency Rule:* If a request to execute preemption is repeated for an already interrupted job, the engine detects the prior transition and returns an idempotent HTTP 200 response without duplicating queue entries or mutating other assignments.

---

### I. Simulation State & Event Log

#### `GET /simulation/state`
Returns the complete fleet, active work orders, technician assignments, and reschedule queue:
```json
{
  "simulation_time": 1729587120.0,
  "simulation_time_iso": "2026-10-22T08:52:00+00:00",
  "fleet_status": {
    "total_machines": 10,
    "machines": {}
  },
  "technician_fleet": {
    "total_technicians": 3,
    "technicians": {
      "TECH-01": {
        "technician_id": "TECH-01",
        "active_job_id": "JOB-EMERGENCY",
        "interrupted_jobs": ["JOB-001"]
      }
    }
  },
  "active_jobs": {
    "JOB-EMERGENCY": {"job_id": "JOB-EMERGENCY", "status": "in_progress", "technician_id": "TECH-01"}
  },
  "reschedule_queue": [
    {"job_id": "JOB-001", "status": "interrupted", "machine_id": "CNC-001"}
  ],
  "total_events_recorded": 14,
  "latest_event_id": 14
}
```

#### `GET /simulation/events?since=<cursor>&limit=<limit>`
Returns all events with `event_id > cursor`:
```json
[
  {
    "event_id": 1,
    "timestamp": 1729587100.0,
    "timestamp_iso": "2026-10-22T08:51:40+00:00",
    "event_type": "PREDICTION_BATCH",
    "machine_id": null,
    "job_id": null,
    "technician_id": null,
    "outcome": "PREDICTED",
    "reason": "Generated predictions for 3 fleet machines.",
    "before_state": null,
    "after_state": null,
    "metadata": {"machine_count": 3}
  },
  {
    "event_id": 2,
    "timestamp": 1729587110.0,
    "timestamp_iso": "2026-10-22T08:51:50+00:00",
    "event_type": "PREEMPTION_EXECUTED",
    "machine_id": "PRESS-09",
    "job_id": "JOB-EMERGENCY",
    "technician_id": "TECH-01",
    "outcome": "EXECUTED",
    "reason": "Preemption authorized...",
    "before_state": {"active_job_id": "JOB-001", "status": "in_progress"},
    "after_state": {"active_job_id": "JOB-EMERGENCY", "status": "in_progress"},
    "metadata": {}
  }
]
```

---

## 4. Additional Scheduling Data Specification

To ensure total clarity between Person 2 (Decision Engine) and the Live Simulation / Orchestration Layer, the table below documents the status of all scheduling entities:

| Category | Field Name | Status | Source / Provider | Description |
|---|---|---|---|---|
| **Maintenance Job Estimates** | `job_id` | **Accepted (Required)** | Orchestration / Caller | Unique work order identifier (e.g. `JOB-101`). |
| | `machine_id` | **Accepted (Required)** | Orchestration / Caller | Target machine identifier. |
| | `job_type` | **Accepted (Optional)** | Orchestration / Config | Work category (`routine_inspection`, `emergency_repair`, etc.). |
| | `estimated_repair_duration` | *Simulation-Supplied* | Simulation / Person 3 | Estimated repair duration in minutes/hours. Not modeled by core decision engine. |
| | `safe_shutdown_duration` | *Simulation-Supplied* | Simulation / Person 3 | Duration required for spin-down and thermal stabilization. |
| | `travel_dispatch_time` | *Simulation-Supplied* | Simulation / Logistics | Travel time from technician depot to factory cell. |
| | `time_to_resume_work` | *Simulation-Supplied* | Simulation / Person 3 | Setup time when resuming a paused work order. |
| **Active Job State** | `status` | **Accepted (Required)** | Engine & Simulation | State: `pending`, `dispatched`, `in_progress`, `interrupted`, `completed`. |
| | `progress` | **Accepted (Optional)** | Simulation / Technician | Preserved across interruptions (`steps`, `percentage`). |
| | `maintenance_stage` | **Accepted (Optional)** | Safety Context | Operational stage checked for reversibility (`inspection`, `welding`). |
| | `is_reversible_stage` | **Accepted (Optional)** | Safety Context | Boolean flag; `False` blocks safe interruption. |
| | `technician_id` | **Accepted (Optional)** | Scheduler / Dispatch | Assigned technician ID; enforces single-active-job invariant. |
| **Production Impact** | `loss_per_downtime_hour` | *Simulation-Supplied* | ERP / Orchestration | Hourly financial downtime rate ($/hour). |
| | `affected_line_ids` | *Simulation-Supplied* | MES / Topology | Upstream/downstream lines affected by cell shutdown. |
| | `backup_machine_available`| *Simulation-Supplied* | MES / Inventory | Redundant machine availability status. |
| **Spare Parts** | `required_part_ids` | *Simulation-Supplied* | ERP / WMS | Bill of materials for target repair. |
| | `part_availability_status`| *Simulation-Supplied* | ERP / WMS | `in_stock`, `on_order`, `missing`. |
| | `expected_delivery_time` | *Simulation-Supplied* | ERP / Supply Chain | Estimated replenishment ETA. |
| **Failure Timing** | `failure_probability` | **Accepted (Required)** | Person 1 ML Model | Model estimated probability of failure in next shift. |
| | `remaining_useful_life` | **Explicitly Unsupported**| ML Model (If added) | **Never derived from failure probability alone.** Marked null unless Person 1 delivers a regression RUL model. |
| | `prediction_horizon` | **Accepted (Optional)** | Person 1 ML Model | Operational forecast horizon (e.g. `next_shift_8h`). Null if not defined. |
| **Technician Fleet** | `technician_id` | **Accepted (Required)** | Dispatch / Fleet | Stable technician identifier (`TECH-01`). |
| | `skills_certifications` | *Simulation-Supplied* | HR / Fleet Manager | Technician qualification matrix. |
| | `shift_id` | **Accepted (Optional)** | Multi-Shift Scheduler | Assigned shift identifier (`SHIFT-1`). |

---

## 5. Cost Breakdown Specification

ForgeGuard's decision engine uses an objective cost model representing **relative operational penalty units** ($C_{\text{FN}}$ and $C_{\text{FP}}$). In executive mode, monetary conversion transforms penalty units into financial estimates.

| Cost Component | Units | Currency | Source | Time Horizon | Included Consequences | Missing Value Handling |
|---|---|---|---|---|---|---|
| **False Negative Cost ($C_{\text{FN}}$)** | Penalty Units | Relative (Default: 20.0) | Configured | Next Shift | Unplanned breakdown, collateral damage, emergency line stoppage, overtime premium. | Defaults to `DEFAULT_FALSE_NEGATIVE_COST` (20.0). |
| **False Positive Cost ($C_{\text{FP}}$)** | Penalty Units | Relative (Default: 1.0) | Configured | Next Shift | Unnecessary technician dispatch, brief inspection stoppage, minor scheduling disruption. | Defaults to `DEFAULT_FALSE_POSITIVE_COST` (1.0). |
| **Monetary Conversion Rate** | Currency / Unit | Configured (e.g. $500 / unit) | Financial Policy | Shift / Annual | Monetary multiplier translating penalty units into executive dollar estimates. | Marked `None` if monetary config is not provided. |
| **Maintenance Labor Cost** | Currency ($) | USD / EUR | Simulation Layer | Per Job | Technician hourly wage multiplied by active duration. | Supplied by simulation; not assumed by decision engine. |
| **Parts / Material Cost** | Currency ($) | USD / EUR | Simulation Layer | Per Job | Replacement component hardware and consumable cost. | Supplied by simulation; not assumed by decision engine. |
| **Production Downtime Cost** | Currency ($) | USD / EUR | Simulation Layer | Hourly Rate | Factory throughput loss per idle machine hour. | Supplied by simulation; not assumed by decision engine. |
| **Job Delay Cost** | Currency ($) | USD / EUR | Simulation Layer | Shift Horizon | Penalty incurred when an alerted job is deferred across consecutive shifts. | Evaluated via [`evaluate_deferred_risk()`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/deferred_risk.py). |
| **Interruption Cost** | Penalty / Currency | Configured | Policy / Preemption | Instantaneous | Penalty incurred for safe-stopping and resuming an active job. | Evaluated via [`PreemptionConfig`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/preemption.py). |

*Double-Counting Avoidance:* Safety assessment rules and hazard containment procedures are evaluated independently as hard constraints and are **never** factored into the cost minimization objective.
