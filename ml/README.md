# ForgeGuard ML Component: PS 2.1 Maintenance Shift Planner

## Overview
This package delivers the production-ready machine learning module for **ForgeGuard**, predicting industrial equipment failure risk and diagnosing failure modes for the NEXTAI HACK 2026 hackathon (Problem Statement 2.1: Maintenance Shift Planner).

---

## Architecture & Directory Layout

```
ml/
├── __init__.py           # Package exports (predict_machines, explain_machine, etc.)
├── data/
│   └── ai4i2020.csv      # UCI AI4I 2020 Predictive Maintenance Dataset
├── preprocessing.py      # Validation and domain-specific physics feature engineering
├── model.py              # ForgeGuardModel container (binary + multi-output diagnosis)
├── train.py              # Reproducible training pipeline & threshold optimizer
├── predict.py            # Stable inference interfaces for engine and UI
├── artifacts/
│   ├── model.joblib      # Fitted scikit-learn model pipeline artifact (~878 KB)
│   └── metadata.json     # Detailed evaluation metrics, threshold curve, and data info
└── README.md             # Integration documentation and model cards
tests/
├── conftest.py           # Test configuration and path setup
└── test_ml.py            # 18 passing unit and integration tests
```

---

## Stable Public Integration Interface

Downstream components (decision engine in `engine/` and dashboard in `app.py` / `ui/`) consume predictions via:

```python
from ml.predict import predict_machines, explain_machine

# Batch telemetry prediction
predictions_df = predict_machines(telemetry_df)
```

### Input Contract:
A `pandas.DataFrame` with at least these telemetry feature columns:
- `Type`: Machine quality grade (`'L'`, `'M'`, or `'H'`)
- `Air temperature [K]`: Ambient factory temperature
- `Process temperature [K]`: Internal operating process temperature
- `Rotational speed [rpm]`: Spindle/motor speed
- `Torque [Nm]`: Mechanical torque load
- `Tool wear [min]`: Tool elapsed cutting minutes

*Note: Target labels (`Machine failure`, `TWF`, `HDF`, etc.) and identity columns (`UDI`, `Product ID`) are NOT required.*

### Output Contract:
Returns a `pandas.DataFrame` preserving input row count and row order with:
- `machine_id`: Supplied identifier (or generated stable row ID `M_0, M_1, ...`)
- `failure_probability`: Float between `0.0` and `1.0`
- `predicted_failure_mode`: Diagnosed failure mode string:
  - `"None"`: Normal operating machine (below decision threshold)
  - `"HDF"`: Heat Dissipation Failure
  - `"PWF"`: Power Failure
  - `"OSF"`: Overstrain Failure
  - `"TWF"`: Tool Wear Failure
  - `"RNF"`: Random Failure
  - Multi-label combinations (e.g., `"PWF, OSF"`) for multi-stress machines
- `maintenance_alert`: Boolean flag (`True` if `failure_probability >= threshold`)

### Explainability Helper:
For maintenance ticket generation and shift technician briefings:
```python
explanation = explain_machine(telemetry_reading_dict, machine_id="CNC_04")
# Returns:
# - recommended_action: e.g. "Immediate technician assignment: Inspect Excess Power Load."
# - telemetry_metrics: {temp_difference_K: ..., mechanical_power_W: ..., overstrain_min_Nm: ...}
# - risk_factors: [list of critical and warning threshold violations]
```

---

## Cost Model & Threshold Optimization

Predicting failure is only the input; the goal is minimizing operational factory cost under technician constraints.
- **Cost Formulation**: $\text{Cost} = 20 \times FN + 1 \times FP$
  - Missed failure ($FN$): $20\times$ penalty (unplanned factory line stoppage, catastrophic damage)
  - False alarm inspection ($FP$): $1\times$ penalty (technician inspection time)
- **Validation Threshold**: Selected via grid sweep on validation set.
  - Default threshold ($0.50$): Validation Cost = $190.0$ ($9$ missed failures)
  - Optimal threshold ($0.270$): Validation Cost = $113.0$ ($40.5\%$ cost reduction)

---

## Held-Out Test Evaluation Results

Evaluated on preserved, untouched $15\%$ held-out test split ($1,500$ machines, $51$ failures):
- **ROC-AUC**: `0.9858`
- **PR-AUC**: `0.8875`
- **Recall (Optimal Threshold 0.270)**: `88.24%` ($45 / 51$ failures caught)
- **Precision**: `45.92%`
- **F1-Score**: `0.6040`
- **Confusion Matrix**: `TN=1396, FP=53, FN=6, TP=45`

---

## Run Commands

```bash
# Run training pipeline (from repository root)
python ml/train.py

# Run test suite
pytest -v tests/test_ml.py
```

---

## Dataset Disclosure & Limitations
1. **Synthetic Nature**: AI4I 2020 is a synthetic benchmark generated from physical machine models. Results do not guarantee identical performance on real-world plant machinery.
2. **Rare Failure Modes**: Some failure modes (such as `TWF` with 46 total cases and `RNF` with 19 cases) have limited support.
3. **Random Failures (`RNF`)**: In the AI4I dataset, `RNF` was injected at random ($0.1\%$ probability) without deterministic sensor signatures, limiting pattern predictability.
