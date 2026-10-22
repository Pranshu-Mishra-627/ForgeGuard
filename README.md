# ForgeGuard — Maintenance Shift Planner

## Person 2: Decision Engine Documentation

This repository implements the **Decision Engine** for NexAI Hack 2026 Problem Statement 2.1 (*Maintenance Shift Planner*). It is responsible for cost modeling, validation-based threshold optimization, and priority-based technician capacity scheduling.

---

## 1. Architecture & Module Structure

```
ForgeGuard/
├── engine/
│   ├── __init__.py           # Exports public API (plan_shift, plan_multi_shift, evaluate_preemption, choose_threshold, calculate_business_impact, evaluate_deferred_risk, evaluate_guardrails, app, api)
│   ├── api.py                # FastAPI HTTP application and REST endpoints for live simulation
│   ├── prediction_service.py # Single and batch prediction adapters for Person 1 ML integration
│   ├── simulation.py         # Live simulation state manager and pull-based event logger
│   ├── preemption.py         # Preemptive maintenance scheduling, safe interruption & reschedule management
│   ├── PREEMPTION.md         # Dedicated documentation for Preemptive Maintenance Scheduling
│   ├── safety_assessment.py  # Data-driven equipment safety rules, telemetry validation & uncertainty handling
│   ├── policy_guardrails.py  # Maintenance policy guardrails, mandatory review & deferral compliance
│   ├── POLICY_GUARDRAILS.md  # Dedicated documentation for Maintenance Policy Guardrails
│   ├── multi_shift_scheduler.py # Multi-shift technician planning, carry-forward deferrals & utilization
│   ├── MULTI_SHIFT.md        # Dedicated documentation for Multi-Shift Maintenance Planner
│   ├── business_impact.py    # Cost savings, confusion count impact & executive monetary projections
│   ├── BUSINESS_IMPACT.md    # Dedicated documentation for Cost Savings & Business Impact feature
│   ├── deferred_risk.py      # Deferred-machine risk ranking, risk tiers & follow-up escalation
│   ├── DEFERRED_RISK.md      # Dedicated documentation for Deferred-Machine Risk Management
│   ├── file_utils.py         # Dynamic file and format loading utilities
│   ├── cost_model.py         # Cost parameter configuration and evaluation
│   ├── threshold.py          # Validation-based threshold grid search & cost curve calculation
│   ├── scheduler.py          # Alert filtering, priority scoring, and capacity-constrained dispatching
│   └── pipeline.py           # End-to-end integration with Person 1's ML predictions
├── configs/                  # Externalized JSON configuration files
├── tests/
│   ├── __init__.py
│   ├── test_api.py           # Integration tests for FastAPI endpoints, error handling, and simulation
│   ├── test_safety_assessment.py # Unit tests for data-driven safety checks, stale/missing data & priority separation
│   ├── test_preemption.py    # Unit tests for preemptive scheduling, invariants, and guardrail integration
│   ├── test_policy_guardrails.py # Unit tests for policy guardrails, review rules, and deferral limits
│   ├── test_multi_shift.py   # Unit tests for multi-shift planning, carry-forward, and utilization
│   ├── test_business_impact.py # Unit tests for cost savings, monetary conversion, and business impact
│   ├── test_deferred_risk.py # Unit tests for deferred risk ranking, risk tiers, and escalation
│   ├── test_file_loading.py  # Tests for dynamic external configuration loading
│   ├── test_cost_model.py    # Unit tests for cost model and threshold optimization
│   ├── test_scheduler.py     # Unit tests for scheduler, capacity constraints, and edge cases
│   ├── test_integration.py   # Integration tests with ML outputs
│   └── test_pipeline_integration.py # Full pipeline integration tests
├── API_REFERENCE.md          # Complete API documentation, schemas, scheduling data, and cost breakdown
└── README.md
```

---

## 2. Decision Logic & Formulas

### Relative Cost Model (`engine/cost_model.py`)
- **Formula**: `total_cost = (false_negative_cost * FN) + (false_positive_cost * FP)`
- **Default Relative Costs**:
  - `false_negative_cost = 20.0` (Missed failure penalty)
  - `false_positive_cost = 1.0` (False alarm dispatch penalty)
- *Note*: Costs are relative operational penalty units, not raw currency. Both parameters are independently configurable.

### Threshold Selection (`engine/threshold.py`)
- Evaluates candidate thresholds across a fixed, documented 101-point grid from `0.00` to `1.00` (step `0.01`).
- Predicts failure when `probability >= threshold`.
- Computes TP, TN, FP, FN, and total operational cost at each grid point.
- **Tie-Breaking Rule**: When multiple candidate thresholds achieve the identical minimum total cost, the **highest threshold** is selected. This minimizes false alarms and dispatch fatigue for maintenance crews without increasing operational cost.

### Shift Scheduler (`engine/scheduler.py`)
- **Alert Rule**: A machine triggers an alert if `failure_probability >= threshold`.
- **Priority Scoring**: `priority_score = failure_probability * false_negative_cost`.
- **Alert Ranking**: Alerted machines are ranked by descending priority score.
- **Tie-Breaking Rule**: When priority scores are tied, ties are broken deterministically by sorting machine identifiers in **ascending alphanumeric order** (`'M-001'` before `'M-002'`).
- **Slot Allocation**: Technicians are assigned to at most `slots` highest-priority alerted machines. Non-alerted machines are never assigned. If fewer alerts exist than slots, remaining slots remain unassigned.
- **Explanations**: Every machine receives an explicit explanation justifying whether it was selected, deferred due to limited technician capacity, or not alerted.

---

## 3. Integration Interface & Schemas

### Upstream (Person 1 → Person 2)
Person 1 supplies:
- Validation ground-truth binary labels: `y_val: Iterable[int]` (values in `{0, 1}`)
- Validation failure probabilities: `p_val: Iterable[float]` (values in `[0.0, 1.0]`)
- Fleet machine records: `df: pd.DataFrame` containing `machine_id` (or custom column) and operational failure probabilities.

### Downstream (Person 2 → Person 3)
Person 3 consumes:
1. **Threshold Optimization Result** (`ThresholdResult`):
   - `.threshold` / `.optimal_threshold`: Selected optimal alert threshold (`float`).
   - `.min_cost` / `.optimal_cost`: Minimum total cost achieved (`float`).
   - `.cost_curve`: Full evaluation curve (`pd.DataFrame` with columns: `['threshold', 'tp', 'tn', 'fp', 'fn', 'total_cost', 'fn_cost', 'fp_cost']`).
   - `.chart_data`: Cost curve indexed by candidate threshold, ready for direct plotting in Streamlit with `st.line_chart(result.chart_data["total_cost"])`.
   - `.confusion_matrix`: Dictionary with confusion counts `{'tp': int, 'tn': int, 'fp': int, 'fn': int}` at optimal threshold.
   - `.baseline_comparison`: Dictionary comparing selected threshold against baseline threshold 0.50 (`baseline_threshold`, `baseline_cost`, `cost_difference`, `cost_savings`, `cost_reduction_pct`, `explanation`).
   - `.cost_difference`: Cost savings (`baseline_cost - optimal_cost`) in relative operational penalty units.
   - `.explain()`: Formatted multi-line explainability summary for UI display or logging.

2. **Shift Schedule Result** (`ScheduleResult`):
   - `.selected_machines`: List of machine IDs selected for service (in priority order).
   - `.deferred_machines`: List of alerted machine IDs deferred due to capacity (in priority order).
   - `.unalerted_machines`: List of machine IDs not alerted (probability below threshold).
   - `.alert_status`: Mapping `{machine_id: bool}`.
   - `.selection_reasons`: Mapping `{machine_id: str}`.
   - `.audit_summary`: Compact operational summary dictionary (threshold, slots, costs, counts, capacity utilization).
   - `.schedule_table`: Complete decision table (`pd.DataFrame`) with columns:
     - `machine_id`: Stable machine identifier.
     - `failure_probability`: Machine failure probability in `[0.0, 1.0]`.
     - `alert`: Boolean indicator (`probability >= threshold`).
     - `priority_score`: Expected failure impact score.
     - `selected_for_service`: Boolean dispatch flag.
     - `reason`: Explicit operational explanation.

3. **End-to-End Pipeline Result** (`PipelineResult`):
   - Combined table with Person 1 features (`machine_id`, `failure_probability`, `predicted_failure_mode`, `maintenance_alert`) and Person 2 decision fields (`operational_alert`, `priority_score`, `service_assignment`, `decision_reason`).
   - Includes `.audit_summary`, `.selected_machines`, `.deferred_machines`, and `.unalerted_machines`.

---

## 4. Quickstart Example

```python
import pandas as pd
from engine import choose_threshold, plan_shift, CostConfig

# 1. Validation data (from Person 1)
y_val = [0, 0, 0, 0, 1, 0, 1, 1, 1, 1]
p_val = [0.12, 0.25, 0.30, 0.42, 0.48, 0.52, 0.68, 0.74, 0.88, 0.95]

# 2. Select optimal threshold
thresh_res = choose_threshold(y_true=y_val, probabilities=p_val)
print(f"Optimal threshold: {thresh_res.threshold} (min cost: {thresh_res.min_cost})")

# 3. Operational fleet scheduling
fleet_df = pd.DataFrame({
    "machine_id": ["CNC-01", "CNC-02", "CNC-03", "PRESS-01", "ROBOT-01"],
    "location": ["Bay-A", "Bay-A", "Bay-B", "Bay-B", "Bay-C"],
})
fleet_probs = [0.92, 0.78, 0.55, 0.51, 0.35]
technician_slots = 3

plan = plan_shift(
    df=fleet_df,
    probabilities=fleet_probs,
    slots=technician_slots,
    threshold=thresh_res.threshold,
)

# 4. Inspect results (for Person 3 Dashboard)
print("Selected machines:", plan.selected_machines)
print("Deferred alerts:", plan.deferred_machines)
print(plan.schedule_table[["machine_id", "alert", "selected_for_service", "reason"]])
```

---

## 5. Running Tests

Run all unit tests with pytest from the project root:

```bash
pytest -v
```
