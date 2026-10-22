# ForgeGuard Decision Engine — Deferred-Machine Risk Management

## 1. Overview

The **Deferred-Machine Risk Management** module (`engine/deferred_risk.py`) provides visibility, deterministic risk ranking, and actionable escalation follow-ups for machines that triggered operational failure alerts but could not be dispatched during the current shift due to technician slot capacity constraints.

---

## 2. Policy Principles & Safety Guarantees

1. **Strict Identification of Deferred Machines**:
   - A machine is classified as **deferred** if and only if:
     $$\text{operational\_alert} == \text{True} \quad \text{AND} \quad \text{selected\_for\_service} == \text{False}$$
   - Non-alerted machines ($\text{probability} < \text{threshold}$) are **never** classified as deferred.
   - Assigned machines ($\text{selected\_for\_service} == \text{True}$) are **never** classified as deferred.

2. **Deterministic Risk Ranking**:
   - Deferred machines are sorted by:
     1. Primary: Descending $\text{priority\_score} = \text{failure\_probability} \times C_{FN}$
     2. Secondary (Tie-Breaking): Ascending alphanumeric machine identifier (e.g. `'M-001'` before `'M-002'`).

3. **No Unbudgeted Dispatching**:
   - Recommendations **never** silently assign extra technicians or exceed the current shift slot capacity.
   - Escalation recommendations provide immediate supervisor awareness, telemetry reviews, and parts staging.

4. **No Presumption of Next-Shift Assignment**:
   - Lower-tier deferred machines are queued as **candidates for re-evaluation** during subsequent shift planning, conditioned on technician capacity and updated sensor readings.

5. **Probabilistic Calibrated Phrasing**:
   - Never claims a machine will definitely fail; reports estimated failure probabilities and risk tiers accurately.

---

## 3. Configurable Risk Tiers & Escalation Matrix

Default configuration ([`RiskTierConfig`](file:///c:/Users/win%2010/OneDrive/Desktop/ForgeGuard/engine/deferred_risk.py#L20-L54)):

| Risk Tier | Probability Range | Escalation Status | Follow-Up Action Recommendation |
| :--- | :---: | :---: | :--- |
| **Critical** | $p \ge 0.80$ | `Escalated` | **Immediate Supervisor Review**: Inspect vibration/thermal signatures, verify safety interlocks, and assess operating load reduction. |
| **High** | $0.60 \le p < 0.80$ | `Escalated` | **Expedited Engineering Review**: Continuous sensor trend monitoring; confirm replacement part availability in inventory. |
| **Medium** | $0.40 \le p < 0.60$ | `Standard Review` | **Queue for Next Shift Review**: Priority candidate for next shift planning; maintain standard automated telemetry logging. |
| **Low** | $p < 0.40$ | `Standard Review` | **Routine Monitoring**: Maintain regular automated condition monitoring cycles. |

---

## 4. Public API Reference

```python
from engine.deferred_risk import evaluate_deferred_risk, RiskTierConfig

# Option A: From a completed ScheduleResult
shift_plan = plan_shift(df=fleet_df, probabilities=probs, slots=2, threshold=0.50)
deferred_plan = evaluate_deferred_risk(shift_plan)

# Option B: With customized risk tier thresholds
custom_cfg = RiskTierConfig(critical_threshold=0.85, high_threshold=0.65, medium_threshold=0.45)
deferred_plan = evaluate_deferred_risk(shift_plan, config=custom_cfg)

# Option C: Direct property access
deferred_plan = shift_plan.deferred_risk
```

### Result Schema (`DeferredRiskResult`)

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `deferred_machines` | `list[DeferredMachineRisk]` | Ranked deferred machine records |
| `risk_table` | `pd.DataFrame` | Structured DataFrame containing all deferred machines and actions |
| `critical_machines` | `list[Any]` | Machine IDs in Critical risk tier |
| `high_risk_machines` | `list[Any]` | Machine IDs in High risk tier |
| `escalated_machines` | `list[Any]` | Machine IDs requiring managerial escalation |
| `audit_summary` | `dict[str, Any]` | Summary counts, breakdown by tier, and escalation rate |
| `explain()` | `str` | Executive-ready formatted report |

---

## 5. Person 3 Streamlit Integration Example

```python
import streamlit as st
from engine import plan_shift, evaluate_deferred_risk

# 1. Schedule shift
plan = plan_shift(df=fleet_df, probabilities=fleet_probs, slots=2, threshold=0.50)

# 2. Evaluate deferred machine risk
deferred_res = evaluate_deferred_risk(plan)

# 3. Streamlit Display
st.subheader("Deferred Machine Risk & Escalation")
if len(deferred_res) > 0:
    st.dataframe(deferred_res.risk_table[[
        "machine_id", "failure_probability", "risk_tier", "escalation_status", "recommendation"
    ]])
    if deferred_res.critical_machines:
        st.error(f"Critical Deferred Alerts: {deferred_res.critical_machines}")
else:
    st.success("All operational alerts accommodated within technician slot capacity!")
```
