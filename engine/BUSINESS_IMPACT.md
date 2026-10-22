# ForgeGuard Decision Engine — Cost Savings & Business Impact Analysis

## Overview

The **Cost Savings & Business Impact** module (`engine/business_impact.py`) translates Person 2's validation-based threshold optimization and relative operational penalty costs into actionable executive business intelligence, cost savings metrics, confusion count tracking, and optional monetary projections for the maintenance leadership team and Person 3's Streamlit dashboard.

---

## 1. Decision Logic & Formulas

### Operational Cost Baseline Comparison
ForgeGuard benchmarks the cost-optimized threshold against a standardized baseline threshold of **0.50** (the industry default classification threshold):
- **Decision Rule**: A machine triggers a maintenance alert when predicted failure probability $\ge \text{threshold}$.
- **Baseline Rule**: Evaluated strictly at threshold $0.50$ on validation data ($\text{probability} \ge 0.50$), never substituted with an arbitrary or nearest candidate grid threshold.

### Core Formulas

1. **Relative Operational Cost Savings**:
   $$\text{cost\_savings} = \text{baseline\_cost} - \text{optimized\_cost}$$
   - Positive ($\text{savings} > 0$): Demonstrates operational penalty reduction.
   - Zero ($\text{savings} = 0$): Optimal threshold matches baseline cost.
   - Negative ($\text{savings} < 0$): Demonstrates a cost increase, reported honestly without claiming a benefit.

2. **Percentage Savings**:
   $$\text{percentage\_savings} = \begin{cases} \frac{\text{baseline\_cost} - \text{optimized\_cost}}{\text{baseline\_cost}} \times 100\% & \text{if } \text{baseline\_cost} > 0 \\ 0.0\% & \text{if } \text{baseline\_cost} = 0 \end{cases}$$
   - Division-by-zero is safely handled when baseline cost is zero.

3. **Cost Increase Percentage (for Negative Savings)**:
   $$\text{cost\_increase\_pct} = \begin{cases} \frac{\text{optimized\_cost} - \text{baseline\_cost}}{\text{baseline\_cost}} \times 100\% & \text{if } \text{baseline\_cost} > 0 \text{ and } \text{optimized\_cost} > \text{baseline\_cost} \\ 0.0\% & \text{otherwise} \end{cases}$$
   - Clearly flags when a threshold increases costs without claiming benefit.

4. **Confusion Matrix Impact**:
   - False Positives (False Alarms):
     $$\Delta\text{FP} = \text{optimized\_fp} - \text{baseline\_fp}, \quad \text{fp\_reduction} = \text{baseline\_fp} - \text{optimized\_fp}$$
   - False Negatives (Missed Failures):
     $$\Delta\text{FN} = \text{optimized\_fn} - \text{baseline\_fn}, \quad \text{fn\_reduction} = \text{baseline\_fn} - \text{optimized\_fn}$$

5. **Optional Monetary Valuation**:
   When configured with a monetary conversion rate ($\text{value\_per\_unit}$, e.g. \$500/penalty unit):
   $$\text{monetary\_savings} = \text{cost\_savings} \times \text{value\_per\_unit}$$
   $$\text{monetary\_baseline\_cost} = \text{baseline\_cost} \times \text{value\_per\_unit}$$
   $$\text{monetary\_optimized\_cost} = \text{optimized\_cost} \times \text{value\_per\_unit}$$
   - When no monetary conversion is configured, all monetary fields remain `None` and are omitted from executive explanations.

---

## 2. Public API Reference

### `calculate_business_impact(...)`
Computes business impact from a `ThresholdResult` or explicit cost parameters:

```python
from engine.business_impact import calculate_business_impact, MonetaryConfig

# Option A: Directly from ThresholdResult
res = choose_threshold(y_true=y_val, probabilities=p_val)
impact = calculate_business_impact(res, monetary_value_per_unit=250.0, currency="USD")

# Option B: Explicit baseline and optimized values
impact = calculate_business_impact(
    baseline_cost=100.0,
    optimized_cost=70.0,
    baseline_confusion={"tp": 8, "tn": 40, "fp": 5, "fn": 7},
    optimized_confusion={"tp": 14, "tn": 43, "fp": 2, "fn": 1},
)
```

### Result Schema (`BusinessImpactResult`)

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `baseline_threshold` | `float` | Fixed at standard 0.50 |
| `optimal_threshold` | `float` | Cost-minimized operational threshold |
| `baseline_cost` | `float` | Operational cost at threshold 0.50 |
| `optimized_cost` | `float` | Operational cost at optimal threshold |
| `cost_savings` | `float` | Cost reduction (`baseline_cost - optimized_cost`) |
| `percentage_savings` | `float` | Percent cost reduction relative to baseline |
| `cost_increase_pct` | `float` | Percent cost increase if costs increased |
| `is_benefit` | `bool` | `True` if cost was reduced or tied, `False` if increased |
| `fp_reduction` | `int` | False alarm reduction count |
| `fn_reduction` | `int` | Missed failure reduction count |
| `monetary_savings` | `float \| None` | Quantified currency savings (or `None`) |
| `currency` | `str \| None` | Currency code/symbol (or `None`) |
| `explanation` | `str` | Formatted multi-line executive explanation |

---

## 3. Person 3 Streamlit Dashboard Integration

Person 3 can integrate `BusinessImpactResult` directly into Streamlit without complex data wrangling:

```python
import streamlit as st
from engine import choose_threshold, calculate_business_impact

# 1. Optimize threshold
thresh_res = choose_threshold(y_true=y_val, probabilities=p_val)

# 2. Calculate business impact with monetary conversion ($500 per cost unit)
impact = calculate_business_impact(thresh_res, monetary_value_per_unit=500.0, currency="USD")

# 3. Streamlit KPI Cards
col1, col2, col3 = st.columns(3)
col1.metric("Operational Cost", f"{impact.optimized_cost:.1f} pts", delta=f"{-impact.cost_savings:.1f} pts")
col2.metric("Cost Savings", f"{impact.percentage_savings:.1f}%", delta=f"{impact.cost_savings:.1f} pts")
if impact.monetary_savings is not None:
    col3.metric("Projected Dollar Savings", f"${impact.monetary_savings:,.0f} USD")

# 4. Executive Narrative
if impact.is_benefit:
    st.success(impact.explain())
else:
    st.warning(impact.explain())
```

---

## 4. Edge Cases Handled

1. **Zero-Cost Baseline**:
   When `baseline_cost == 0.0`, `percentage_savings` is safely set to `0.0%` without raising `ZeroDivisionError`.
2. **Negative Savings (Cost Increase)**:
   When `optimized_cost > baseline_cost`, savings are negative and reported as an honest cost increase (`is_benefit = False`), never mislabeled as a benefit.
3. **Missing Monetary Configuration**:
   When no `monetary_value_per_unit` is provided, all monetary fields remain `None` and monetary text is cleanly omitted.
4. **Custom Grid Threshold Baseline**:
   Always evaluates against genuine threshold `0.50`, even when a candidate grid excludes `0.50`.
