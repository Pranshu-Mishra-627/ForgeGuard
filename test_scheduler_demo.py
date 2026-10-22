"""Demonstration script for shift scheduler decision engine.

Tests 5 machines with:
- probabilities: [0.92, 0.75, 0.60, 0.45, 0.20]
- threshold: 0.50
- slots: 3
- missed-failure cost: 20
- false-alarm cost: 1
"""

import pandas as pd
from engine.cost_model import CostConfig
from engine.scheduler import plan_shift


def main() -> None:
    # 1. Define inputs
    machines = ["M-01", "M-02", "M-03", "M-04", "M-05"]
    probabilities = [0.92, 0.75, 0.60, 0.45, 0.20]
    threshold = 0.50
    slots = 3
    costs = CostConfig(false_negative_cost=20.0, false_positive_cost=1.0)

    df = pd.DataFrame({"machine_id": machines})

    # 2. Run shift planning
    result = plan_shift(
        df=df,
        probabilities=probabilities,
        slots=slots,
        threshold=threshold,
        costs=costs,
    )

    # 3. Assertions & verification
    assert result.selected_machines == ["M-01", "M-02", "M-03"], (
        f"Expected ['M-01', 'M-02', 'M-03'] selected in priority order, got {result.selected_machines}"
    )
    assert result.deferred_machines == [], (
        f"Expected empty deferred list, got {result.deferred_machines}"
    )
    assert result.alert_status["M-04"] is False, "Expected M-04 unalerted"
    assert result.alert_status["M-05"] is False, "Expected M-05 unalerted"

    # 4. Display results
    print("=" * 80)
    print("FORGEGUARD MAINTENANCE SHIFT PLANNER -- DECISION ENGINE DEMO")
    print("=" * 80)
    print(f"Configured Alert Threshold : {threshold:.2f}")
    print(f"Technician Slots Available : {slots}")
    print(f"Missed Failure Cost (FN)   : {costs.false_negative_cost}")
    print(f"False Alarm Cost (FP)      : {costs.false_positive_cost}")
    print("-" * 80)
    print(f"Selected for Service (in priority order) : {result.selected_machines}")
    print(f"Deferred Alerted Machines                 : {result.deferred_machines}")
    print("-" * 80)
    print("\nCOMPLETE SHIFT PLAN TABLE:")
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 1000)
    print(result.schedule_table.to_string(index=False))

    print("\nDETAILED DECISION EXPLANATIONS:")
    for mid, reason in result.selection_reasons.items():
        status = "SELECTED" if mid in result.selected_machines else ("DEFERRED" if result.alert_status[mid] else "NOT ALERTED")
        print(f"  [{mid}] ({status}): {reason}")

    print("\n" + "=" * 80)
    print("VERIFICATION CHECK: ALL CONDITIONS SATISFIED SUCCESSFULLY")
    print("=" * 80)


if __name__ == "__main__":
    main()
