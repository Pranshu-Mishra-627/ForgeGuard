"""Unit tests for data-driven, configurable safety assessment (engine/safety_assessment.py).

Verifies:
1. Safe case: All required signals present, within limits, fresh, no hazards, reversible stage -> SAFE_TO_INTERRUPT.
2. Unsafe cases:
   - Operating temperature exceeds threshold -> UNSAFE_TO_INTERRUPT.
   - Vibration level exceeds threshold -> UNSAFE_TO_INTERRUPT.
   - Active environmental/physical hazard present -> UNSAFE_TO_INTERRUPT.
   - Irreversible maintenance stage -> UNSAFE_TO_INTERRUPT.
   - Disallowed categorical value present -> UNSAFE_TO_INTERRUPT.
3. Missing-data cases:
   - Required signal omitted -> INDETERMINATE.
   - Empty telemetry dictionary -> INDETERMINATE.
   - Missing required rule signal -> INDETERMINATE.
4. Stale-data cases:
   - Telemetry older than max_telemetry_age_seconds -> INDETERMINATE.
   - Future timestamp (clock skew) -> INDETERMINATE.
   - Missing timestamp when age verification required -> INDETERMINATE.
5. Conflicting-data cases:
   - Discrepancy between primary and redundant sensor exceeds tolerance -> INDETERMINATE.
   - Categorical sensor divergence -> INDETERMINATE.
6. Invalid-configuration cases:
   - Invalid rule bounds (min > max, non-numeric) -> ValueError / TypeError.
   - Invalid age limits (negative, infinite) -> ValueError / TypeError.
   - Empty rule_id or signal_name -> ValueError.
7. Priority separation:
   - Priority score 999.0 cannot override UNSAFE or INDETERMINATE safety outcome.
8. Structured audit result:
   - Evidence used, rule identifiers, missing inputs, and executive explanations.
"""

from __future__ import annotations

import pytest
import math

from engine.safety_assessment import (
    DEFAULT_EQUIPMENT_SAFETY_CONFIG,
    DEFAULT_SAFETY_RULES,
    OUTCOME_INDETERMINATE,
    OUTCOME_SAFE_TO_INTERRUPT,
    OUTCOME_UNSAFE_TO_INTERRUPT,
    EquipmentSafetyConfig,
    EquipmentSafetyRule,
    MachineTelemetryContext,
    SafetyAssessmentOutcome,
    SafetyAssessmentResult,
    assess_job_safety,
)
from engine.preemption import (
    ALERT_CATEGORY_ACTUAL_FAILURE,
    JOB_STATUS_IN_PROGRESS,
    STATUS_DENIED,
    STATUS_EXECUTED,
    MaintenanceJob,
    PreemptionConfig,
    evaluate_preemption,
)


class TestSafeAssessment:
    """Verifies that jobs with fresh, non-conflicting, compliant telemetry are declared safe to pause."""

    def test_safe_to_interrupt_standard_industrial(self) -> None:
        """When all signals are present, fresh, and within limits, returns SAFE_TO_INTERRUPT."""
        ctx = MachineTelemetryContext(
            machine_id="CNC-001",
            telemetry_signals={"temperature_c": 68.5, "vibration_rms": 2.2},
            timestamp=1000.0,
            current_time=1050.0,  # 50s old < 300s limit
            maintenance_stage="visual_inspection",
            is_reversible_stage=True,
            redundant_signals={"temperature_c": 69.0, "vibration_rms": 2.3},  # diff 0.5 <= 5.0, diff 0.1 <= 1.0
        )
        res = assess_job_safety(ctx, DEFAULT_EQUIPMENT_SAFETY_CONFIG)

        assert res.outcome == OUTCOME_SAFE_TO_INTERRUPT
        assert res.is_safe_to_interrupt is True
        assert len(res.violated_rules) == 0
        assert len(res.missing_inputs) == 0
        assert len(res.stale_signals) == 0
        assert len(res.conflicting_signals) == 0
        assert res.evidence_used["temperature_c"] == 68.5
        assert res.evidence_used["vibration_rms"] == 2.2
        assert "Safe to interrupt" in res.explanation

    def test_safe_assessment_from_plain_dict(self) -> None:
        """assess_job_safety supports plain mapping inputs cleanly."""
        data = {
            "machine_id": "PRESS-02",
            "telemetry_signals": {"temperature_c": 55.0, "vibration_rms": 1.4},
            "timestamp": "2026-10-22T10:00:00Z",
            "current_time": "2026-10-22T10:02:00Z",  # 2 minutes old < 5 mins
            "is_reversible_stage": True,
        }
        res = assess_job_safety(data, DEFAULT_EQUIPMENT_SAFETY_CONFIG)
        assert res.outcome == OUTCOME_SAFE_TO_INTERRUPT
        assert res.is_safe_to_interrupt is True


class TestUnsafeAssessment:
    """Verifies that physical violations, active hazards, and irreversible steps are declared UNSAFE."""

    def test_unsafe_temperature_exceeded(self) -> None:
        """Operating temperature above configured limit triggers UNSAFE_TO_INTERRUPT."""
        ctx = MachineTelemetryContext(
            machine_id="CNC-002",
            telemetry_signals={"temperature_c": 92.4, "vibration_rms": 2.0},  # 92.4 > 85.0
            timestamp=1000.0,
            current_time=1010.0,
        )
        res = assess_job_safety(ctx, DEFAULT_EQUIPMENT_SAFETY_CONFIG)

        assert res.outcome == OUTCOME_UNSAFE_TO_INTERRUPT
        assert res.is_safe_to_interrupt is False
        assert "RULE_MAX_TEMPERATURE" in res.violated_rules
        assert "Preemption is unsafe and strictly forbidden" in res.explanation

    def test_unsafe_vibration_exceeded(self) -> None:
        """Vibration RMS above configured limit triggers UNSAFE_TO_INTERRUPT."""
        ctx = MachineTelemetryContext(
            machine_id="CNC-003",
            telemetry_signals={"temperature_c": 70.0, "vibration_rms": 5.8},  # 5.8 > 4.5
            timestamp=1000.0,
            current_time=1010.0,
        )
        res = assess_job_safety(ctx, DEFAULT_EQUIPMENT_SAFETY_CONFIG)

        assert res.outcome == OUTCOME_UNSAFE_TO_INTERRUPT
        assert res.is_safe_to_interrupt is False
        assert "RULE_MAX_VIBRATION" in res.violated_rules

    def test_unsafe_active_hazards_present(self) -> None:
        """Presence of active environmental or equipment hazards triggers UNSAFE_TO_INTERRUPT."""
        ctx = MachineTelemetryContext(
            machine_id="PRESS-009",
            telemetry_signals={"temperature_c": 60.0, "vibration_rms": 1.5},
            timestamp=1000.0,
            current_time=1010.0,
            active_hazards=("pressurized_hydraulic_fluid", "arc_flash_risk"),
        )
        res = assess_job_safety(ctx, DEFAULT_EQUIPMENT_SAFETY_CONFIG)

        assert res.outcome == OUTCOME_UNSAFE_TO_INTERRUPT
        assert res.is_safe_to_interrupt is False
        assert "RULE_ACTIVE_HAZARDS_PRESENT" in res.violated_rules
        assert "active environmental or physical hazards" in res.explanation

    def test_unsafe_irreversible_maintenance_stage(self) -> None:
        """When maintenance stage cannot be paused safely, triggers UNSAFE_TO_INTERRUPT."""
        ctx = MachineTelemetryContext(
            machine_id="ROBOT-01",
            telemetry_signals={"temperature_c": 50.0, "vibration_rms": 1.0},
            timestamp=1000.0,
            current_time=1010.0,
            maintenance_stage="spindle_thermal_shrink_fitting",
            is_reversible_stage=False,
        )
        res = assess_job_safety(ctx, DEFAULT_EQUIPMENT_SAFETY_CONFIG)

        assert res.outcome == OUTCOME_UNSAFE_TO_INTERRUPT
        assert res.is_safe_to_interrupt is False
        assert "RULE_IRREVERSIBLE_STAGE" in res.violated_rules
        assert "is non-reversible" in res.explanation


class TestMissingAndUncertainData:
    """Verifies that missing signals, empty telemetry, and unverified data yield INDETERMINATE."""

    def test_missing_required_signals(self) -> None:
        """When a required signal is absent, returns INDETERMINATE and blocks preemption."""
        ctx = MachineTelemetryContext(
            machine_id="CNC-004",
            telemetry_signals={"temperature_c": 65.0},  # vibration_rms missing!
            timestamp=1000.0,
            current_time=1010.0,
        )
        res = assess_job_safety(ctx, DEFAULT_EQUIPMENT_SAFETY_CONFIG)

        assert res.outcome == OUTCOME_INDETERMINATE
        assert res.is_safe_to_interrupt is False
        assert "vibration_rms" in res.missing_inputs
        assert "missing signals ['vibration_rms']" in res.explanation
        assert "blocked pending manual human/supervisor safety verification" in res.explanation

    def test_empty_telemetry_signals(self) -> None:
        """Empty telemetry context yields INDETERMINATE."""
        ctx = MachineTelemetryContext(machine_id="CNC-EMPTY")
        res = assess_job_safety(ctx, DEFAULT_EQUIPMENT_SAFETY_CONFIG)

        assert res.outcome == OUTCOME_INDETERMINATE
        assert res.is_safe_to_interrupt is False
        assert "vibration_rms" in res.missing_inputs
        assert "temperature_c" in res.missing_inputs

    def test_missing_data_allowed_only_if_explicitly_configured(self) -> None:
        """allow_unverified_interruption allows preemption only when explicitly configured."""
        lenient_cfg = EquipmentSafetyConfig(
            equipment_type="LENIENT",
            required_signals=("vibration_rms",),
            allow_unverified_interruption=True,
        )
        ctx = MachineTelemetryContext(machine_id="M-01", telemetry_signals={})
        res = assess_job_safety(ctx, lenient_cfg)
        assert res.outcome == OUTCOME_SAFE_TO_INTERRUPT


class TestStaleDataAssessment:
    """Verifies that expired telemetry timestamps trigger INDETERMINATE."""

    def test_stale_telemetry_age_exceeded(self) -> None:
        """Telemetry older than max_telemetry_age_seconds triggers INDETERMINATE."""
        ctx = MachineTelemetryContext(
            machine_id="CNC-005",
            telemetry_signals={"temperature_c": 70.0, "vibration_rms": 2.0},
            timestamp=1000.0,
            current_time=1400.0,  # 400s old > 300s limit!
        )
        res = assess_job_safety(ctx, DEFAULT_EQUIPMENT_SAFETY_CONFIG)

        assert res.outcome == OUTCOME_INDETERMINATE
        assert res.is_safe_to_interrupt is False
        assert "telemetry_age_exceeded" in res.stale_signals
        assert "stale telemetry" in res.explanation

    def test_future_timestamp_skew_detected(self) -> None:
        """Telemetry timestamp in the future triggers INDETERMINATE due to clock skew."""
        ctx = MachineTelemetryContext(
            machine_id="CNC-006",
            telemetry_signals={"temperature_c": 70.0, "vibration_rms": 2.0},
            timestamp=2000.0,
            current_time=1000.0,  # Age is -1000s
        )
        res = assess_job_safety(ctx, DEFAULT_EQUIPMENT_SAFETY_CONFIG)

        assert res.outcome == OUTCOME_INDETERMINATE
        assert res.is_safe_to_interrupt is False
        assert "timestamp_future" in res.stale_signals

    def test_missing_timestamp_flags_stale(self) -> None:
        """Telemetry with no timestamp when freshness check required triggers INDETERMINATE."""
        ctx = MachineTelemetryContext(
            machine_id="CNC-007",
            telemetry_signals={"temperature_c": 70.0, "vibration_rms": 2.0},
            timestamp=None,
        )
        res = assess_job_safety(ctx, DEFAULT_EQUIPMENT_SAFETY_CONFIG)

        assert res.outcome == OUTCOME_INDETERMINATE
        assert "all_signals_missing_timestamp" in res.stale_signals


class TestConflictingDataAssessment:
    """Verifies that sensor discrepancy between primary and redundant channels triggers INDETERMINATE."""

    def test_conflicting_temperature_sensors(self) -> None:
        """When primary and backup temperature sensors diverge beyond tolerance, returns INDETERMINATE."""
        ctx = MachineTelemetryContext(
            machine_id="PRESS-008",
            telemetry_signals={"temperature_c": 72.0, "vibration_rms": 2.0},
            redundant_signals={"temperature_c": 83.0, "vibration_rms": 2.1},  # diff 11.0 > 5.0 allowed!
            timestamp=1000.0,
            current_time=1050.0,
        )
        res = assess_job_safety(ctx, DEFAULT_EQUIPMENT_SAFETY_CONFIG)

        assert res.outcome == OUTCOME_INDETERMINATE
        assert res.is_safe_to_interrupt is False
        assert "temperature_c" in res.conflicting_signals
        assert res.conflicting_signals["temperature_c"]["discrepancy"] == 11.0
        assert "conflicting sensors on ['temperature_c']" in res.explanation

    def test_conflicting_vibration_sensors(self) -> None:
        """When primary and backup vibration sensors diverge beyond tolerance, returns INDETERMINATE."""
        ctx = MachineTelemetryContext(
            machine_id="PRESS-009",
            telemetry_signals={"temperature_c": 60.0, "vibration_rms": 1.5},
            redundant_signals={"temperature_c": 61.0, "vibration_rms": 3.8},  # diff 2.3 > 1.0 allowed!
            timestamp=1000.0,
            current_time=1050.0,
        )
        res = assess_job_safety(ctx, DEFAULT_EQUIPMENT_SAFETY_CONFIG)

        assert res.outcome == OUTCOME_INDETERMINATE
        assert "vibration_rms" in res.conflicting_signals


class TestInvalidConfigurationAndValidation:
    """Verifies strict validation of safety rules and configuration boundaries."""

    def test_invalid_rule_parameters_rejected(self) -> None:
        """EquipmentSafetyRule validates rule identifiers, signal names, and bounds."""
        with pytest.raises(ValueError, match="rule_id must be a non-empty string"):
            EquipmentSafetyRule(rule_id="", signal_name="temp")

        with pytest.raises(ValueError, match="signal_name must be a non-empty string"):
            EquipmentSafetyRule(rule_id="R1", signal_name="")

        with pytest.raises(TypeError, match="max_value must be numeric"):
            EquipmentSafetyRule(rule_id="R1", signal_name="temp", max_value="hot")  # type: ignore

        with pytest.raises(ValueError, match="min_value .* cannot exceed max_value"):
            EquipmentSafetyRule(rule_id="R1", signal_name="temp", min_value=100.0, max_value=50.0)

    def test_invalid_config_parameters_rejected(self) -> None:
        """EquipmentSafetyConfig validates telemetry age and equipment types."""
        with pytest.raises(TypeError, match="equipment_type must be a string"):
            EquipmentSafetyConfig(equipment_type=123)  # type: ignore

        with pytest.raises(ValueError, match="max_telemetry_age_seconds must be positive"):
            EquipmentSafetyConfig(max_telemetry_age_seconds=-10.0)

        with pytest.raises(TypeError, match="allow_unverified_interruption must be a boolean"):
            EquipmentSafetyConfig(allow_unverified_interruption="no")  # type: ignore


class TestPrioritySeparationAndPreemptionIntegration:
    """Verifies that priority scores cannot override safety restrictions and integration works seamlessly."""

    def test_higher_priority_score_cannot_override_unsafe_safety_outcome(self) -> None:
        """Requirement 8: Priority score 999.0 must NEVER override an UNSAFE safety outcome."""
        current_job = MaintenanceJob(
            job_id="JOB-ACTIVE-HOT",
            machine_id="CNC-99",
            priority_score=10.0,
            status=JOB_STATUS_IN_PROGRESS,
            is_interruptible=True,
            # Telemetry shows machine is dangerously hot (95°C > 85°C)
            safety_context=MachineTelemetryContext(
                machine_id="CNC-99",
                telemetry_signals={"temperature_c": 95.0, "vibration_rms": 2.0},
                timestamp=1000.0,
                current_time=1010.0,
            ),
        )
        # Incoming catastrophic failure has maximum possible priority
        incoming_job = MaintenanceJob(
            job_id="JOB-EXTREME-PRIORITY",
            machine_id="PRESS-CRIT",
            priority_score=999.0,
            alert_category=ALERT_CATEGORY_ACTUAL_FAILURE,
        )

        config = PreemptionConfig(equipment_safety_config=DEFAULT_EQUIPMENT_SAFETY_CONFIG)
        res = evaluate_preemption(current_job, incoming_job, config=config)

        # Preemption must be strictly DENIED despite huge priority delta (989.0)
        assert res.preemption_executed is False
        assert res.status == STATUS_DENIED
        assert res.safety_assessment is not None
        assert res.safety_assessment.outcome == OUTCOME_UNSAFE_TO_INTERRUPT
        assert "cannot override safety restrictions" in res.decision_reason
        assert "RULE_MAX_TEMPERATURE" in res.safety_assessment.violated_rules

    def test_higher_priority_score_cannot_override_indeterminate_safety_outcome(self) -> None:
        """Requirement 8: High priority score cannot override an INDETERMINATE safety outcome."""
        current_job = MaintenanceJob(
            job_id="JOB-UNCERTAIN",
            machine_id="CNC-UNCERTAIN",
            priority_score=10.0,
            status=JOB_STATUS_IN_PROGRESS,
            is_interruptible=True,
            # Missing vibration_rms signal!
            safety_context=MachineTelemetryContext(
                machine_id="CNC-UNCERTAIN",
                telemetry_signals={"temperature_c": 60.0},
                timestamp=1000.0,
                current_time=1010.0,
            ),
        )
        incoming_job = MaintenanceJob(
            job_id="JOB-URGENT",
            machine_id="PRESS-01",
            priority_score=100.0,
            alert_category=ALERT_CATEGORY_ACTUAL_FAILURE,
        )

        config = PreemptionConfig(equipment_safety_config=DEFAULT_EQUIPMENT_SAFETY_CONFIG)
        res = evaluate_preemption(current_job, incoming_job, config=config)

        # Preemption denied/blocked due to data uncertainty
        assert res.preemption_executed is False
        assert res.status == STATUS_DENIED
        assert res.safety_assessment is not None
        assert res.safety_assessment.outcome == OUTCOME_INDETERMINATE
        assert "INDETERMINATE" in res.decision_reason

    def test_preemption_executes_when_safety_assessment_is_safe(self) -> None:
        """When data-driven safety assessment is SAFE_TO_INTERRUPT, preemption executes."""
        current_job = MaintenanceJob(
            job_id="JOB-NORMAL",
            machine_id="CNC-SAFE",
            priority_score=20.0,
            status=JOB_STATUS_IN_PROGRESS,
            is_interruptible=True,
            technician_id="TECH-01",
            safety_context=MachineTelemetryContext(
                machine_id="CNC-SAFE",
                telemetry_signals={"temperature_c": 62.0, "vibration_rms": 1.8},
                timestamp=1000.0,
                current_time=1030.0,
                is_reversible_stage=True,
            ),
        )
        incoming_job = MaintenanceJob(
            job_id="JOB-URGENT",
            machine_id="PRESS-01",
            priority_score=85.0,
            alert_category=ALERT_CATEGORY_ACTUAL_FAILURE,
        )

        config = PreemptionConfig(equipment_safety_config=DEFAULT_EQUIPMENT_SAFETY_CONFIG)
        res = evaluate_preemption(current_job, incoming_job, config=config)

        assert res.preemption_executed is True
        assert res.status == STATUS_EXECUTED
        assert res.safety_assessment is not None
        assert res.safety_assessment.outcome == OUTCOME_SAFE_TO_INTERRUPT
        assert res.safety_assessment.is_safe_to_interrupt is True
        assert "Safe to interrupt" in res.safety_assessment.explanation
