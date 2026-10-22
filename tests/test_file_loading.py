"""Unit and integration tests for dynamic, zero-hardcoding file loading and serialization.

Verifies that all decision engine configurations, datasets, telemetry contexts,
safety rules, shifts, and job records can be loaded dynamically from external
files (JSON and CSV) without any hardcoded assumptions or paths.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
import pandas as pd

from engine import (
    CostConfig,
    RiskTierConfig,
    MaintenancePolicyConfig,
    ShiftConfig,
    EquipmentSafetyConfig,
    EquipmentSafetyRule,
    MachineTelemetryContext,
    MaintenanceJob,
    PreemptionConfig,
    plan_shift,
    plan_multi_shift,
    assess_job_safety,
    evaluate_preemption,
    integrate_predictions,
    load_dataframe_or_path,
    load_json_or_dict,
    save_json,
    OUTCOME_SAFE_TO_INTERRUPT,
)


class TestConfigFilesInConfigsDir:
    """Verifies that the external configuration templates in configs/ are valid and loadable."""

    def test_load_cost_parameters_json(self) -> None:
        path = Path("configs/cost_parameters.json")
        assert path.is_file(), "configs/cost_parameters.json must exist"
        cfg = CostConfig.from_file(path)
        assert cfg.false_negative_cost == 20.0
        assert cfg.false_positive_cost == 1.0

    def test_load_equipment_safety_rules_json(self) -> None:
        path = Path("configs/equipment_safety_rules.json")
        assert path.is_file(), "configs/equipment_safety_rules.json must exist"
        cfg = EquipmentSafetyConfig.from_file(path)
        assert cfg.equipment_type == "CNC_MILL"
        assert len(cfg.rules) == 2
        assert "temperature_c" in cfg.required_signals
        assert "vibration_rms" in cfg.required_signals

    def test_load_preemption_rules_json(self) -> None:
        path = Path("configs/preemption_rules.json")
        assert path.is_file(), "configs/preemption_rules.json must exist"
        cfg = PreemptionConfig.from_file(path)
        assert cfg.enabled is True
        assert cfg.min_priority_delta == 5.0
        assert "actual_failure" in cfg.allowed_alert_categories

    def test_load_maintenance_policies_json(self) -> None:
        path = Path("configs/maintenance_policies.json")
        assert path.is_file(), "configs/maintenance_policies.json must exist"
        cfg = MaintenancePolicyConfig.from_file(path)
        assert cfg.mandatory_review_critical is True
        assert cfg.risk_config.critical_threshold == 0.80

    def test_load_shifts_schedule_json(self) -> None:
        path = Path("configs/shifts_schedule.json")
        assert path.is_file(), "configs/shifts_schedule.json must exist"
        shifts = ShiftConfig.load_shifts(path)
        assert len(shifts) == 3
        assert shifts[0].shift_id == "Shift_1_Morning"
        assert shifts[0].capacity == 3


class TestConfigurationSerialization:
    """Verifies roundtrip serialization (to_dict/from_dict, to_file/from_file) for all configs."""

    def test_cost_config_file_roundtrip(self, tmp_path: Path) -> None:
        file_path = tmp_path / "custom_costs.json"
        orig = CostConfig(false_negative_cost=35.0, false_positive_cost=2.5)
        orig.to_file(file_path)
        loaded = CostConfig.from_file(file_path)
        assert loaded.false_negative_cost == 35.0
        assert loaded.false_positive_cost == 2.5

    def test_risk_tier_config_file_roundtrip(self, tmp_path: Path) -> None:
        file_path = tmp_path / "custom_risk.json"
        orig = RiskTierConfig(critical_threshold=0.85, high_threshold=0.65, medium_threshold=0.45)
        orig.to_file(file_path)
        loaded = RiskTierConfig.from_file(file_path)
        assert loaded.critical_threshold == 0.85
        assert loaded.high_threshold == 0.65
        assert loaded.medium_threshold == 0.45

    def test_maintenance_policy_config_file_roundtrip(self, tmp_path: Path) -> None:
        file_path = tmp_path / "custom_policy.json"
        orig = MaintenancePolicyConfig(max_consecutive_deferrals=3, mandatory_review_critical=False)
        orig.to_file(file_path)
        loaded = MaintenancePolicyConfig.from_file(file_path)
        assert loaded.max_consecutive_deferrals == 3
        assert loaded.mandatory_review_critical is False

    def test_shift_config_file_roundtrip_json_and_csv(self, tmp_path: Path) -> None:
        # JSON list
        json_path = tmp_path / "shifts.json"
        shifts = [ShiftConfig("Day", 4), ShiftConfig("Night", 2)]
        ShiftConfig.save_shifts(shifts, json_path)
        loaded_json = ShiftConfig.load_shifts(json_path)
        assert len(loaded_json) == 2
        assert loaded_json[0].shift_id == "Day"
        assert loaded_json[0].capacity == 4

        # CSV list
        csv_path = tmp_path / "shifts.csv"
        pd.DataFrame([{"shift_id": "Alpha", "capacity": 5}, {"shift_id": "Beta", "capacity": 3}]).to_csv(csv_path, index=False)
        loaded_csv = ShiftConfig.load_shifts(csv_path)
        assert len(loaded_csv) == 2
        assert loaded_csv[0].shift_id == "Alpha"
        assert loaded_csv[0].capacity == 5

    def test_telemetry_context_file_roundtrip(self, tmp_path: Path) -> None:
        file_path = tmp_path / "telemetry_ctx.json"
        ctx = MachineTelemetryContext(
            machine_id="CNC-99",
            telemetry_signals={"temperature_c": 62.5, "vibration_rms": 1.9},
            timestamp=100.0,
            current_time=120.0,
            is_reversible_stage=True,
        )
        ctx.to_file(file_path)
        loaded = MachineTelemetryContext.from_file(file_path)
        assert loaded.machine_id == "CNC-99"
        assert loaded.telemetry_signals["temperature_c"] == 62.5
        assert loaded.is_reversible_stage is True

    def test_maintenance_job_file_roundtrip_json_and_csv(self, tmp_path: Path) -> None:
        # Single job JSON
        job_file = tmp_path / "job.json"
        job = MaintenanceJob(
            job_id="JOB-01",
            machine_id="PRESS-04",
            priority_score=85.0,
            job_type="preventive_maintenance",
            is_interruptible=True,
        )
        job.to_file(job_file)
        loaded = MaintenanceJob.from_file(job_file)
        assert loaded.job_id == "JOB-01"
        assert loaded.priority_score == 85.0

        # Multi-job CSV
        csv_file = tmp_path / "jobs.csv"
        pd.DataFrame([
            {"job_id": "J1", "machine_id": "M1", "priority_score": 50.0},
            {"job_id": "J2", "machine_id": "M2", "priority_score": 90.0},
        ]).to_csv(csv_file, index=False)
        loaded_jobs = MaintenanceJob.from_file(csv_file)
        assert len(loaded_jobs) == 2
        assert loaded_jobs[1].job_id == "J2"
        assert loaded_jobs[1].priority_score == 90.0


class TestDynamicFileExecutionInEngine:
    """Verifies that engine functions accept external file paths directly without hardcoding."""

    def test_plan_shift_from_csv_and_json_cost(self, tmp_path: Path) -> None:
        # Create CSV fleet
        fleet_csv = tmp_path / "fleet.csv"
        pd.DataFrame({
            "machine_id": ["M-1", "M-2", "M-3"],
            "failure_probability": [0.95, 0.70, 0.20],
        }).to_csv(fleet_csv, index=False)

        # Create JSON cost config
        cost_json = tmp_path / "costs.json"
        CostConfig(false_negative_cost=25.0, false_positive_cost=1.5).to_file(cost_json)

        # Plan shift directly from file paths!
        plan = plan_shift(df=fleet_csv, slots=1, threshold=0.50, costs=cost_json)
        assert plan.selected_machines == ["M-1"]
        assert plan.deferred_machines == ["M-2"]
        assert plan.costs.false_negative_cost == 25.0

    def test_plan_multi_shift_from_files(self, tmp_path: Path) -> None:
        # Predictions CSV
        preds_csv = tmp_path / "predictions.csv"
        pd.DataFrame({
            "machine_id": ["M-A", "M-B", "M-C", "M-D"],
            "failure_probability": [0.92, 0.85, 0.65, 0.15],
            "predicted_failure_mode": ["Bearing", "Heat", "Electrical", "None"],
        }).to_csv(preds_csv, index=False)

        # Shifts JSON
        shifts_json = tmp_path / "shifts.json"
        ShiftConfig.save_shifts([ShiftConfig("S1", 1), ShiftConfig("S2", 1)], shifts_json)

        # Run multi-shift directly from file paths
        result = plan_multi_shift(
            schedule_or_df=preds_csv,
            shifts=shifts_json,
            threshold=0.50,
            costs="configs/cost_parameters.json",
        )
        assert result.assigned_machines == ["M-A", "M-B"]
        assert result.still_deferred_machines == ["M-C"]

    def test_assess_job_safety_from_files(self, tmp_path: Path) -> None:
        ctx_file = tmp_path / "telemetry_context.json"
        MachineTelemetryContext(
            machine_id="M-10",
            telemetry_signals={"temperature_c": 60.0, "vibration_rms": 2.0},
            timestamp=500.0,
            current_time=550.0,
            is_reversible_stage=True,
        ).to_file(ctx_file)

        res = assess_job_safety(
            context=ctx_file,
            config="configs/equipment_safety_rules.json",
        )
        assert res.outcome == OUTCOME_SAFE_TO_INTERRUPT
        assert res.is_safe_to_interrupt is True

    def test_evaluate_preemption_from_files(self, tmp_path: Path) -> None:
        curr_file = tmp_path / "current_job.json"
        inc_file = tmp_path / "incoming_job.json"

        MaintenanceJob(
            job_id="CURR-01",
            machine_id="M-1",
            priority_score=15.0,
            job_type="preventive_maintenance",
            is_interruptible=True,
            status="in_progress",
        ).to_file(curr_file)

        MaintenanceJob(
            job_id="INC-01",
            machine_id="M-2",
            priority_score=95.0,
            alert_category="actual_failure",
        ).to_file(inc_file)

        decision = evaluate_preemption(
            current_job=curr_file,
            incoming_job=inc_file,
            config="configs/preemption_rules.json",
        )
        assert decision.status == "executed"
        assert decision.interrupted_job_id == "CURR-01"
        assert decision.incoming_job_id == "INC-01"

    def test_integrate_predictions_from_file(self, tmp_path: Path) -> None:
        preds_file = tmp_path / "preds.csv"
        pd.DataFrame({
            "machine_id": ["CNC-1", "CNC-2"],
            "failure_probability": [0.88, 0.22],
            "predicted_failure_mode": ["Bearing", "None"],
        }).to_csv(preds_file, index=False)

        res = integrate_predictions(
            predictions_df=preds_file,
            threshold=0.50,
            slots=1,
            costs="configs/cost_parameters.json",
        )
        assert res.selected_machines == ["CNC-1"]
        assert len(res.combined_table) == 2

    def test_missing_file_raises_filenotfound(self) -> None:
        with pytest.raises(FileNotFoundError):
            plan_shift(df="non_existent_fleet_data.csv", probabilities=[0.5], slots=1, threshold=0.5)

        with pytest.raises(FileNotFoundError):
            CostConfig.from_file("missing_cost_file.json")
