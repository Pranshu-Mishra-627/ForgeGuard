# ForgeGuard Person 2 -- Maintenance Policy Guardrails

The **Maintenance Policy Guardrails** module (`engine/policy_guardrails.py`) establishes compliance, safety, and risk governance across ForgeGuard's scheduling and dispatch decisions. It evaluates operational assignments against managerial policies without overriding technician capacities or altering optimized alert thresholds.

---

## 1. Core Principles

1. **Capacity & Scheduling Safety**: Guardrails never silently create technician slots or exceed shift capacity. A triggered policy recommends urgent review or escalation, but strictly preserves scheduled dispatches.
2. **Decoupled Governance**: Policy rules (such as mandatory supervisor sign-offs and maximum deferral limits) operate independently of cost-optimized threshold selection and shift capacities.
3. **Calibrated Probabilistic Language**: Explanations and reasons avoid deterministic assertions (e.g. *"will fail"*, *"certain to fail"*), using calibrated probabilistic risk framing.
4. **Deterministic Precedence**: When a machine triggers multiple policies simultaneously, a deterministic severity hierarchy determines the primary policy identifier and violation type, while all triggered policies remain auditable in `triggered_policies`.
5. **Truthful Deferral Tracking**: Evaluates existing deferral history where available (e.g. from multi-shift schedules). When history is absent, it never fabricates past shifts.

---

## 2. Deterministic Policy Precedence Hierarchy

| Precedence | Policy Identifier | Severity | Violation Type | Description |
| :---: | :--- | :---: | :--- | :--- |
| **1 (Highest)**| `POL_MAX_DEFERRALS_EXCEEDED` | 100 | `POLICY_VIOLATION` | Machine has been deferred for $\ge$ `max_consecutive_deferrals` shifts. |
| **2** | `POL_CRITICAL_DEFERRED` | 90 | `POLICY_VIOLATION` | Critical risk asset ($p \ge \text{critical\_threshold}$) left unserviced due to capacity. |
| **3** | `POL_HIGH_DEFERRED` | 70 | `ESCALATION_RECOMMENDED` | High risk asset ($p \ge \text{high\_threshold}$) left unserviced due to capacity. |
| **4** | `POL_CRITICAL_ALERT` | 60 | `MANDATORY_REVIEW` | Critical alert dispatched or awaiting dispatch, requiring mandatory supervisor review. |
| **5** | `POL_MEDIUM_DEFERRED` | 40 | `NORMAL_DEFERRAL` | Medium risk asset deferred behind higher-priority units. |
| **6** | `POL_STANDARD_DEFERRAL` | 20 | `NORMAL_DEFERRAL` | Low risk asset deferred under normal shift capacity. |
| **7 (Lowest)** | `POL_COMPLIANT` | 0 | `COMPLIANT` | Normal dispatch or unalerted asset adhering to all policies. |

---

## 3. Configuration Reference (`MaintenancePolicyConfig`)

```python
from engine import MaintenancePolicyConfig, RiskTierConfig

custom_policy = MaintenancePolicyConfig(
    risk_config=RiskTierConfig(critical_threshold=0.80, high_threshold=0.60),
    mandatory_review_critical=True,     # Require human sign-off for critical alerts
    escalate_critical_deferred=True,    # Flag critical unserviced machines for escalation
    escalate_high_deferred=True,        # Flag high-risk unserviced machines for escalation
    max_consecutive_deferrals=2,        # Max allowable consecutive shift deferrals (>= 1)
    enforce_max_deferral_violation=True,# Classify max deferral breaches as POLICY_VIOLATION
    require_review_on_max_deferral=True,# Require human review when limit is reached
    escalate_on_max_deferral=True,      # Trigger escalation when limit is reached
)
```

---

## 4. API Reference & Usage Example

### Evaluating a Scheduled Plan
```python
import pandas as pd
from engine import plan_shift, evaluate_guardrails

fleet_df = pd.DataFrame({
    "machine_id": ["CNC-001", "CNC-002", "CNC-003", "CNC-004"],
    "failure_probability": [0.95, 0.82, 0.65, 0.20],
})

# Plan shift with 1 technician slot
schedule = plan_shift(df=fleet_df, probabilities="failure_probability", slots=1, threshold=0.50)

# Evaluate guardrails
guardrails = schedule.evaluate_guardrails()

# Or call directly
# guardrails = evaluate_guardrails(schedule)

print(guardrails.explain())
```

### Inspecting Guardrail Audit Outputs
```python
# Access executive KPIs
print(f"Total Policy Triggers: {guardrails.policy_triggered_count}")
print(f"Policy Violations: {guardrails.violation_count}")
print(f"Machines Requiring Human Review: {guardrails.review_required_machines}")
print(f"Machines Requiring Escalation: {guardrails.escalated_machines}")

# Access consolidated audit table
df_audit = guardrails.guardrail_table
```
