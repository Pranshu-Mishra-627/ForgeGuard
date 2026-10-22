# ForgeGuard Person 2 -- Multi-Shift Maintenance Planner

The **Multi-Shift Maintenance Planner** (`engine/multi_shift_scheduler.py`) extends ForgeGuard's decision engine across multiple sequential maintenance shifts. It allocates technician capacity, carries forward deferred alerts, prevents duplicate dispatches, preserves full audit history, and reports shift-by-shift utilization.

---

## 1. Core Scheduling Principles

1. **Threshold & Capacity Decoupling**: Operational alert qualification (`failure_probability >= threshold`) is governed exclusively by the cost-optimized threshold derived from validation data. Changing shift capacities or adding shifts never shifts the threshold.
2. **Prioritization with Deterministic Tie-Breaking**: Alerted machines are prioritized by expected failure impact (`priority_score = failure_probability * false_negative_cost`), breaking identical score ties deterministically by ascending alphanumeric `machine_id`.
3. **Sequential Carry-Forward**: Alerted machines that cannot be dispatched in Shift $N$ due to capacity constraints are carried forward as candidates for Shift $N+1$.
4. **Non-Reassignment Invariance**: By default (`allow_reassignment=False`), each machine is assigned to at most one shift across the planning horizon.
5. **Decoupled Escalation**: Critical-risk machines are prominently escalated for managerial oversight, but escalation does not silently create extra technician slots or exceed shift capacity.
6. **Transparent History**: Every machine's record contains its complete deferral history across shifts, its assigned shift, and an auditable decision reason.

---

## 2. API Reference

### `plan_multi_shift(...)`

```python
from engine import plan_multi_shift, ShiftConfig

# Direct planning on fleet DataFrame
result = plan_multi_shift(
    df=fleet_df,
    shifts=[
        ShiftConfig("Shift_1", capacity=2),
        ShiftConfig("Shift_2", capacity=3),
    ],
    probabilities="failure_probability",
    threshold=0.50,
)
```

#### Flexible Shift Formats
The `shifts` parameter accepts:
- `[ShiftConfig("Shift_1", 2), ShiftConfig("Shift_2", 3)]`
- `[("Shift_1", 2), ("Shift_2", 3)]`
- `[{"shift_id": "Shift_1", "capacity": 2}, {"shift_id": "Shift_2", "capacity": 3}]`
- `{"Shift_1": 2, "Shift_2": 3}`
- `[2, 3]` (auto-generates `"Shift_1"`, `"Shift_2"`)

#### From `ScheduleResult` or `PipelineResult`
```python
# Chaining directly from single-shift plan or pipeline
multi_plan = schedule_res.plan_multi_shift(shifts=[("Morning", 1), ("Evening", 2)])
pipeline_plan = pipeline_res.plan_multi_shift(shifts=[("Morning", 1), ("Evening", 2)])
```

---

## 3. Structured Results

### `MultiShiftPlanResult`
- `shifts`: List of configured `ShiftConfig` objects.
- `shift_summaries`: List of `ShiftAssignmentSummary` with `capacity`, `assigned_machines`, `assigned_count`, `unused_slots`, and `utilization_rate`.
- `shift_assignments`: Dictionary mapping `shift_id -> [machine_ids]`.
- `assigned_machines`: All machines dispatched across all shifts in order of dispatch.
- `still_deferred_machines`: Alerted machines unserviced after the final shift.
- `unalerted_machines`: Fleet units that did not trigger an alert.
- `assignments_table`: Consolidated pandas DataFrame.
- `audit_summary`: Executive KPI dictionary.
- `.explain()`: Executive markdown summary report.

### Schema of `assignments_table`
| Column | Type | Description |
| :--- | :--- | :--- |
| `machine_id` | Any | Unique machine identifier |
| `failure_probability` | float | Calibrated failure probability |
| `priority_score` | float | Expected failure impact (`p * C_FN`) |
| `alert` | bool | Operational alert eligibility |
| `risk_tier` | str | Qualitative risk tier (`Critical`, `High`, `Medium`, `Low`) |
| `is_escalated` | bool | Managerial escalation indicator |
| `escalation_status` | str | `'Escalated'` or `'Standard Review'` |
| `assigned_shift` | str / None | Assigned shift ID (or `None` if unserviced) |
| `selected_for_service`| bool | `True` if dispatched in any shift |
| `still_deferred` | bool | `True` if alerted and unserviced after final shift |
| `overall_alert_rank` | int / None | Priority rank among all alerted fleet machines |
| `shift_rank` | int / None | Priority rank within assigned shift |
| `deferral_history` | list[str] | List of earlier shift IDs where unit was deferred |
| `reason` | str | Complete auditable explanation |
| `predicted_failure_mode` | str / None | ML failure mode if present |

---

## 4. Usage Example

```python
import pandas as pd
from engine import plan_multi_shift

fleet_df = pd.DataFrame({
    "machine_id": ["CNC-001", "CNC-002", "CNC-003", "CNC-004", "CNC-005"],
    "failure_probability": [0.92, 0.84, 0.70, 0.60, 0.20],
})

# 4 machines alert (>= 0.50). Shift 1 capacity=1, Shift 2 capacity=2.
result = plan_multi_shift(
    df=fleet_df,
    shifts=[("Shift_1", 1), ("Shift_2", 2)],
    threshold=0.50,
)

print(result.explain())
# Shift 1 dispatches CNC-001 (rank 1)
# Shift 2 dispatches CNC-002 (rank 2) and CNC-003 (rank 3)
# CNC-004 (rank 4) remains still_deferred
# CNC-005 is not alerted
```
