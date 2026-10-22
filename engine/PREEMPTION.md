# ForgeGuard Person 2 -- Preemptive Maintenance Scheduling

The **Preemptive Maintenance Scheduling** module (`engine/preemption.py`) enables the ForgeGuard decision engine to evaluate whether an active, lower-priority maintenance job can be safely paused to reassign a technician to a sudden machine breakdown or urgent failure alert.

---

## 1. Objective & Invariants

When a newly failed or urgently alerted machine has a higher priority score than a technician's currently assigned job, the engine evaluates whether the active job can be safely interrupted. If preemption is permitted and authorized:
1. **The active job is safely paused** and marked as `interrupted` (or `paused`).
2. **Work progress and metadata are preserved** (e.g. progress steps, start time, pause timestamp, interruption reason).
3. **The technician is reassigned** to the incoming urgent job without creating additional technician capacity.
4. **The paused job is placed into a reschedule queue** for subsequent shifts or idle capacity, never marked completed or silently discarded.

### Core Invariants

- **Single-Active-Job Invariant**: A technician must never be assigned to two active jobs simultaneously. Preemption transfers the technician from the interrupted job to the higher-priority job; it does not increase technician capacity.
- **Interruptibility & Safety First**: Jobs are interrupted only if explicitly marked interruptible (`is_interruptible=True`) or if their job type is verified as safely interruptible. If interruptibility or safety cannot be established, preemption is denied and escalated for supervisor review.
- **Decoupled Governance & Authorization**: If policies require human approval (or if guardrails flag mandatory review for critical risks), the engine returns a structured `pending_approval` recommendation rather than executing unauthorized mutation.
- **Truth in Assignment State**: State mutation only occurs when preemption is actually executed (`status == "executed"`). Recommendations and pending approvals preserve current job assignments.
- **Calibrated Probabilistic Phrasing**: Distinguishes actual failures (`actual_failure`) from predicted failure risks (`predicted_high_risk`), avoiding deterministic assertions of future breakdown.

---

## 2. Decision Rules & Evaluation Workflow

A preemption is evaluated and executed only when all of the following conditions are met:

```
+-------------------------------------------------------------------------------+
|                        Incoming Urgent Alert Arrives                          |
+-------------------------------------------------------------------------------+
                                       |
                                       v
         +-------------------------------------------------------------+
         | 1. Is preemption globally enabled?                          |  NO -> Denied
         +-------------------------------------------------------------+
                                       | YES
                                       v
         +-------------------------------------------------------------+
         | 2. Is incoming alert category permitted?                    |  NO -> Denied
         |    (e.g., actual_failure, critical_alert, predicted_risk)   |
         +-------------------------------------------------------------+
                                       | YES
                                       v
         +-------------------------------------------------------------+
         | 3. Does incoming priority exceed current by min_delta?      |  NO -> Denied
         |    (incoming_priority - current_priority >= min_delta)      |
         +-------------------------------------------------------------+
                                       | YES
                                       v
         +-------------------------------------------------------------+
         | 4. Is current job in an interruptible state?                |  NO -> Denied
         |    (in_progress, active, dispatched, pending)               |
         +-------------------------------------------------------------+
                                       | YES
                                       v
         +-------------------------------------------------------------+
         | 5. Can current job be safely interrupted?                   |  NO -> Denied
         |    (explicit flag, non-hazardous work type, metadata check) |        (Escalate)
         +-------------------------------------------------------------+
                                       | YES
                                       v
         +-------------------------------------------------------------+
         | 6. Does preemption require human authorization?             |
         |    (config.require_human_approval OR guardrail policy)      |
         +-------------------------------------------------------------+
                    /                                       \
         YES (not approved)                          NO / APPROVED
                  v                                           v
      +------------------------+                 +------------------------+
      | STATUS_PENDING_APPROVAL|                 |    STATUS_EXECUTED     |
      | Current job preserved  |                 | Pause current job      |
      | Await supervisor sign  |                 | Reassign technician    |
      +------------------------+                 | Add to reschedule queue|
                                                 +------------------------+
```

---

## 3. Configuration Reference (`PreemptionConfig`)

```python
from engine import PreemptionConfig
from engine.policy_guardrails import DEFAULT_POLICY_CONFIG

config = PreemptionConfig(
    enabled=True,                         # Whether preemption evaluation is active
    min_priority_delta=10.0,              # Minimum priority advantage required to interrupt
    allowed_alert_categories=(            # Allowed alert categories
        "actual_failure",
        "critical_alert",
        "predicted_high_risk",
    ),
    require_human_approval=False,         # Require explicit human authorization
    interruptible_job_states=(            # States that can be safely paused
        "in_progress", "active", "dispatched", "pending"
    ),
    interruptible_job_types=(             # Job types safe to interrupt
        "routine_inspection",
        "preventive_maintenance",
        "standard_repair",
        "lubrication",
    ),
    non_interruptible_job_types=(         # Safety-critical work types (never pause)
        "emergency_repair",
        "critical_overhaul",
        "safety_containment",
    ),
    allow_unknown_interruptibility=False, # If False, missing safety metadata denies preemption
    guardrail_config=DEFAULT_POLICY_CONFIG,# Maintenance Policy Guardrails integration
)
```

---

## 4. API Reference & Usage Examples

### Evaluating Preemption Between Two Jobs

```python
from engine import MaintenanceJob, evaluate_preemption, PreemptionConfig

# Active job currently worked on by technician
active_job = MaintenanceJob(
    job_id="JOB-101",
    machine_id="CNC-04",
    priority_score=25.0,
    job_type="preventive_maintenance",
    is_interruptible=True,
    technician_id="TECH-01",
    progress="40% complete",
)

# Incoming sudden failure
urgent_job = MaintenanceJob(
    job_id="JOB-999",
    machine_id="PRESS-01",
    priority_score=95.0,
    alert_category="actual_failure",
)

result = evaluate_preemption(active_job, urgent_job)
print(result.explain())
# Preemption authorized: Actual machine breakdown failure (priority 95.00) exceeds current job...
```

### Executing Preemption and Preserving Work

```python
from engine import execute_preemption

result, paused_job, new_job = execute_preemption(
    active_job,
    urgent_job,
    technician_id="TECH-01",
    timestamp="2026-10-22T14:30:00Z",
)

assert paused_job.status == "interrupted"
assert paused_job.interrupted_at == "2026-10-22T14:30:00Z"
assert paused_job.preempted_by_job_id == "JOB-999"
assert paused_job.progress == "40% complete"  # Progress preserved!

assert new_job.status == "in_progress"
assert new_job.technician_id == "TECH-01"
```

### Managing Technician Fleet with `PreemptionManager`

```python
from engine import PreemptionManager

manager = PreemptionManager()
manager.register_technician("TECH-01", name="Alice")
manager.assign_job("TECH-01", active_job)

# Process incoming failure
result = manager.handle_incoming_alert(urgent_job)

# Single active job per technician maintained
assert manager.get_active_jobs()["TECH-01"].job_id == "JOB-999"

# Interrupted job placed in reschedule queue
reschedule_queue = manager.get_reschedule_queue()
assert len(reschedule_queue) == 1
assert reschedule_queue[0].job_id == "JOB-101"
```

---

## 5. Structured Decision Result (`PreemptionResult`)

| Field | Type | Description |
| :--- | :--- | :--- |
| `preemption_considered` | `bool` | Whether preemption criteria were evaluated. |
| `preemption_executed` | `bool` | Whether reassignment was actually executed. |
| `requires_human_approval` | `bool` | Whether human supervisor approval is required. |
| `technician_id` | `str \| None` | Target technician identifier. |
| `interrupted_job_id` | `str \| None` | Identifier of paused job (None if no preemption). |
| `incoming_job_id` | `Any` | Identifier of incoming high-priority job. |
| `current_priority_score` | `float \| None` | Priority score of the current job. |
| `incoming_priority_score` | `float` | Priority score of the incoming job. |
| `decision_reason` | `str` | Plain-English explanation justifying the decision. |
| `interrupted_job_status` | `str \| None` | State of current job after evaluation (`interrupted`, `in_progress`, etc.). |
| `recommended_action` | `str` | Actionable dispatch or supervisor recommendation. |
| `status` | `str` | Status code (`executed`, `pending_approval`, `recommended`, `denied`, `no_preemption`). |
| `safety_assessment` | `SafetyAssessmentResult \| None` | Structured result of data-driven safety evaluation. |

---

## 6. Data-Driven Safety Assessment (`engine/safety_assessment.py`)

To prevent arbitrary or hardcoded assumptions of interruptibility (`is_interruptible = True`), safety evaluation is decoupled from priority scoring and governed by externalized equipment rules and verified telemetry.

### 6.1 Available Dataset Fields vs. Missing Safety Inputs

| Category | Available in ForgeGuard Data Models | Missing Safety-Critical Inputs |
| :--- | :--- | :--- |
| **Telemetry** | `machine_id`, `vibration_rms`, `temperature_c`, `factory_line` | Operational cycle phase (cutting vs. idle), spindle RPM, hydraulic pressure, thermal runaway indicators |
| **ML Model** | `failure_probability`, `predicted_failure_mode`, `maintenance_alert` | Task reversibility, physical barrier status, chemical/gas hazards |
| **Work Orders** | `status`, `job_type`, `priority_score`, `technician_id` | Granular maintenance procedure step (welding vs. torque vs. inspection), Lockout/Tagout (LOTO) verification |
| **Sensors** | Primary reading only | Sensor freshness timestamps, backup/redundant sensor channels for drift/conflict validation |

> [!IMPORTANT]
> **Safety Cannot Be Inferred From Failure Probabilities Alone**:
> A low or high failure probability (`failure_probability`) indicates predicted asset health, NOT whether an in-progress maintenance intervention can be safely interrupted. Genuine physical safety requires operational telemetry and maintenance context. When safety evidence is absent, the assessment yields `INDETERMINATE`, blocking automatic interruption.

### 6.2 Data-Driven Assessment Outcomes

1. **`SAFE_TO_INTERRUPT`**: Telemetry is fresh, redundant sensors agree within configured tolerances, no active hazards exist, the maintenance stage is reversible, and all equipment safety boundaries are satisfied.
2. **`UNSAFE_TO_INTERRUPT`**: One or more equipment safety limits are breached (e.g. `temperature_c > 85.0°C` or `vibration_rms > 4.5 mm/s`), an active hazard is present, or the maintenance step is irreversible.
3. **`INDETERMINATE`**: Required telemetry is missing, stale (exceeding `max_telemetry_age_seconds`), or conflicting across redundant sensors. Preemption is blocked pending human supervisor verification.

### 6.3 Externalized Equipment Safety Rules (`EquipmentSafetyConfig`)

Equipment limits are defined in configuration data records rather than embedded in Python conditionals:

```python
from engine import (
    EquipmentSafetyConfig,
    EquipmentSafetyRule,
    MachineTelemetryContext,
    assess_job_safety,
)

cnc_safety_config = EquipmentSafetyConfig(
    equipment_type="CNC_MILL_SERIES_4",
    rules=(
        EquipmentSafetyRule(
            rule_id="RULE_MAX_TEMPERATURE",
            signal_name="temperature_c",
            max_value=85.0,
            required=True,
            description="Machine operating temperature must not exceed 85.0°C during pause.",
        ),
        EquipmentSafetyRule(
            rule_id="RULE_MAX_VIBRATION",
            signal_name="vibration_rms",
            max_value=4.5,
            required=True,
            description="Vibration level must not exceed 4.5 mm/s RMS.",
        ),
    ),
    required_signals=("vibration_rms", "temperature_c"),
    max_telemetry_age_seconds=300.0,
    max_signal_discrepancy=(("vibration_rms", 1.0), ("temperature_c", 5.0)),
    allow_unverified_interruption=False,  # Strictly blocks preemption on missing/stale data
)
```

### 6.4 Priority Separation Principle

**A higher priority score must never override a safety restriction.** Even if an incoming alert has an extreme priority score (e.g. `999.0`), an active job evaluated as `UNSAFE_TO_INTERRUPT` or `INDETERMINATE` will strictly block automatic preemption.
