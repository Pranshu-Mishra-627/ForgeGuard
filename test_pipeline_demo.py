"""Demonstration script for end-to-end ML prediction and Decision Engine integration.

Demonstrates:
1. Person 1 telemetry input and predict_machines() output.
2. Person 2 validation-based threshold optimization (choose_threshold).
3. Person 2 shift scheduling with capacity limits (plan_shift).
4. Full combined output DataFrame with all required fields.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from engine import (
    CostConfig,
    PipelineResult,
    choose_threshold,
    predict_and_schedule,
)


def mock_predict_machines(telemetry_df: pd.DataFrame) -> pd.DataFrame:
    """Mock implementation of Person 1's predict_machines(telemetry_df)."""
    # Plausible synthetic probabilities for 5 machines
    probs = [0.94, 0.82, 0.61, 0.44, 0.15]
    modes = [
        "Bearing Wear",
        "Overheating",
        "Tool Wear",
        "Electrical Surge",
        "None",
    ]
    # Person 1's model-internal threshold alert (e.g., fixed at 0.50)
    model_alerts = [p >= 0.50 for p in probs]

    return pd.DataFrame({
        "machine_id": telemetry_df["machine_id"].values,
        "failure_probability": probs,
        "predicted_failure_mode": modes,
        "maintenance_alert": model_alerts,
    })


def main() -> None:
    print("=" * 90)
    print("FORGEGUARD: PERSON 1 (ML) + PERSON 2 (DECISION ENGINE) INTEGRATION DEMO")
    print("=" * 90)

    # 1. Validation data for threshold optimization (Requirement 4)
    # 50 validation samples with ground truth failure labels and predicted probabilities
    rng = np.random.RandomState(42)
    n_val = 50
    y_val = rng.binomial(n=1, p=0.25, size=n_val)
    p_val = np.clip(
        np.where(y_val == 1, rng.beta(5, 2, size=n_val), rng.beta(2, 5, size=n_val)),
        0.01,
        0.99,
    )

    # 2. Configurable costs & technician capacity (Requirements 5 & 8)
    costs = CostConfig(false_negative_cost=20.0, false_positive_cost=1.0)
    technician_slots = 2  # 2 slots available

    # 3. Raw operational telemetry batch (Requirement 2)
    telemetry_df = pd.DataFrame({
        "machine_id": ["CNC-001", "CNC-002", "CNC-003", "CNC-004", "CNC-005"],
        "factory_line": ["Line-A", "Line-A", "Line-B", "Line-B", "Line-B"],
        "vibration_rms": [4.8, 3.9, 3.2, 1.8, 1.1],
        "temperature_c": [88.5, 82.1, 74.0, 58.3, 51.2],
    })

    # 4. Run full integration pipeline
    result: PipelineResult = predict_and_schedule(
        telemetry_df=telemetry_df,
        y_val=y_val,
        p_val=p_val,
        slots=technician_slots,
        costs=costs,
        predict_fn=mock_predict_machines,
    )

    # 5. Display threshold optimization results
    print(f"\n[1] THRESHOLD OPTIMIZATION (Validation Set n={n_val}):")
    print(f"    Selected Operational Threshold : {result.operational_threshold:.2f}")
    if result.threshold_result:
        print(f"    Minimum Validation Cost        : {result.threshold_result.min_cost:.2f}")
        print(f"    Confusion Counts at Threshold  : {result.threshold_result.confusion_matrix}")
        base_comp = result.threshold_result.baseline_comparison
        print(f"    Baseline Comparison (t=0.50)   : {base_comp.get('explanation')}")

    # 6. Display shift schedule overview
    print(f"\n[2] SHIFT CAPACITY & DISPATCH OVERVIEW:")
    print(f"    Available Technician Slots     : {technician_slots}")
    print(f"    Missed Failure Cost (FN)       : {costs.false_negative_cost}")
    print(f"    False Alarm Cost (FP)          : {costs.false_positive_cost}")
    print(f"    Selected for Service           : {result.selected_machines}")
    print(f"    Deferred Alerts (Capacity)     : {result.deferred_machines}")
    print(f"    Unalerted Machines             : {result.unalerted_machines}")
    print(f"    Compact Audit Summary          : {result.audit_summary}")

    # 7. Display complete combined table (Requirement 7)
    print(f"\n[3] COMBINED INTEGRATION TABLE:")
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 1000)
    display_cols = [
        "machine_id",
        "failure_probability",
        "predicted_failure_mode",
        "maintenance_alert",
        "operational_alert",
        "priority_score",
        "service_assignment",
        "decision_reason",
    ]
    print(result.combined_table[display_cols].to_string(index=False))

    print("\n" + "=" * 90)
    print("VERIFICATION CHECK: Pipeline integration completed successfully.")
    print("=" * 90)


if __name__ == "__main__":
    main()
