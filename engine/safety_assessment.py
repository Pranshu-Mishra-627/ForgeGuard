"""Data-driven, configurable safety assessment for ForgeGuard decision engine.

Evaluates whether an active maintenance job can be safely interrupted based on
available equipment telemetry, maintenance context, and externalized safety rules.

Core Principles:
1. No Hardcoded Safety: Does not assume jobs are safe or interruptible by default.
2. Data-Driven Evaluation: Evaluates only genuinely available signals without inventing
   sensor readings, timestamps, or maintenance progress.
3. Separation of Concerns: Safety assessment evaluates evidence, hazards, and uncertainty;
   the preemption policy decides whether to reassign based on priority and governance.
4. Fail-Safe on Uncertainty: If required safety evidence is missing, stale, or conflicting,
   returns an INDETERMINATE outcome and blocks automatic interruption.
5. Priority Never Overrides Safety: A high priority score cannot bypass an UNSAFE or
   INDETERMINATE safety outcome.
6. Configurable Rules: Equipment limits and constraints are defined in validated configuration
   objects rather than machine-specific Python conditionals.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class SafetyAssessmentOutcome(str, Enum):
    """Outcome classification of an interruptibility safety assessment."""

    SAFE_TO_INTERRUPT = "SAFE_TO_INTERRUPT"
    UNSAFE_TO_INTERRUPT = "UNSAFE_TO_INTERRUPT"
    INDETERMINATE = "INDETERMINATE"


OUTCOME_SAFE_TO_INTERRUPT = SafetyAssessmentOutcome.SAFE_TO_INTERRUPT.value
OUTCOME_UNSAFE_TO_INTERRUPT = SafetyAssessmentOutcome.UNSAFE_TO_INTERRUPT.value
OUTCOME_INDETERMINATE = SafetyAssessmentOutcome.INDETERMINATE.value


@dataclass(frozen=True)
class EquipmentSafetyRule:
    """Configurable equipment safety constraint or operational boundary.

    Attributes:
        rule_id: Unique rule identifier (e.g. 'RULE_MAX_TEMPERATURE').
        signal_name: Name of telemetry signal or context parameter evaluated.
        max_value: Optional maximum allowable value (inclusive).
        min_value: Optional minimum allowable value (inclusive).
        allowed_values: Optional sequence of permitted categorical values.
        disallowed_values: Optional sequence of forbidden categorical values.
        required: If True, missing signal immediately triggers INDETERMINATE.
        description: Plain-English explanation of the safety rationale.
    """

    rule_id: str
    signal_name: str
    max_value: float | None = None
    min_value: float | None = None
    allowed_values: tuple[Any, ...] | None = None
    disallowed_values: tuple[Any, ...] | None = None
    required: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        """Validate safety rule parameters."""
        if not isinstance(self.rule_id, str) or not self.rule_id.strip():
            raise ValueError("rule_id must be a non-empty string.")
        if not isinstance(self.signal_name, str) or not self.signal_name.strip():
            raise ValueError("signal_name must be a non-empty string.")
        if self.max_value is not None:
            if isinstance(self.max_value, bool) or not isinstance(self.max_value, (int, float)):
                raise TypeError(f"max_value must be numeric, got {type(self.max_value).__name__}.")
            if not math.isfinite(self.max_value):
                raise ValueError("max_value must be finite.")
        if self.min_value is not None:
            if isinstance(self.min_value, bool) or not isinstance(self.min_value, (int, float)):
                raise TypeError(f"min_value must be numeric, got {type(self.min_value).__name__}.")
            if not math.isfinite(self.min_value):
                raise ValueError("min_value must be finite.")
        if self.max_value is not None and self.min_value is not None:
            if self.min_value > self.max_value:
                raise ValueError(
                    f"min_value ({self.min_value}) cannot exceed max_value ({self.max_value})."
                )

    def to_dict(self) -> dict[str, Any]:
        """Convert rule to dictionary representation."""
        return {
            "rule_id": self.rule_id,
            "signal_name": self.signal_name,
            "max_value": self.max_value,
            "min_value": self.min_value,
            "allowed_values": list(self.allowed_values) if self.allowed_values else None,
            "disallowed_values": list(self.disallowed_values) if self.disallowed_values else None,
            "required": self.required,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> EquipmentSafetyRule:
        """Create rule dynamically from mapping."""
        return cls(
            rule_id=str(d["rule_id"]),
            signal_name=str(d["signal_name"]),
            max_value=float(d["max_value"]) if d.get("max_value") is not None else None,
            min_value=float(d["min_value"]) if d.get("min_value") is not None else None,
            allowed_values=tuple(d["allowed_values"]) if d.get("allowed_values") else None,
            disallowed_values=tuple(d["disallowed_values"]) if d.get("disallowed_values") else None,
            required=bool(d.get("required", True)),
            description=str(d.get("description", "")),
        )

    @classmethod
    def from_file(cls, filepath: str | Any) -> EquipmentSafetyRule:
        """Load EquipmentSafetyRule dynamically from external JSON file."""
        import json
        from pathlib import Path

        path = Path(filepath)
        if not path.is_file():
            raise FileNotFoundError(f"Equipment safety rule file not found: {filepath}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_file(self, filepath: str | Any) -> None:
        """Export EquipmentSafetyRule to an external JSON file."""
        import json
        from pathlib import Path

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)


@dataclass(frozen=True)
class EquipmentSafetyConfig:
    """Externalized, validated safety rules and equipment tolerances.

    Attributes:
        equipment_type: Model or category of equipment (e.g. 'CNC_MILL', 'PRESS').
        rules: Tuple of EquipmentSafetyRule objects defining limits.
        required_signals: Signals that must be present and valid for assessment.
        max_telemetry_age_seconds: Max allowable age of telemetry data before flagging stale.
        max_signal_discrepancy: Allowable divergence between primary and redundant sensors.
        allow_unverified_interruption: If False (default), missing/uncertain data blocks preemption.
    """

    equipment_type: str = "DEFAULT"
    rules: tuple[EquipmentSafetyRule, ...] = field(default_factory=tuple)
    required_signals: tuple[str, ...] = ("vibration_rms", "temperature_c")
    max_telemetry_age_seconds: float | None = 300.0  # 5 minutes
    max_signal_discrepancy: tuple[tuple[str, float], ...] = (
        ("vibration_rms", 1.0),
        ("temperature_c", 5.0),
    )
    allow_unverified_interruption: bool = False

    def __post_init__(self) -> None:
        """Validate safety configuration."""
        if not isinstance(self.equipment_type, str):
            raise TypeError("equipment_type must be a string.")
        if self.max_telemetry_age_seconds is not None:
            if isinstance(self.max_telemetry_age_seconds, bool) or not isinstance(
                self.max_telemetry_age_seconds, (int, float)
            ):
                raise TypeError("max_telemetry_age_seconds must be numeric.")
            if self.max_telemetry_age_seconds <= 0.0 or not math.isfinite(
                self.max_telemetry_age_seconds
            ):
                raise ValueError("max_telemetry_age_seconds must be positive and finite.")
        if not isinstance(self.allow_unverified_interruption, bool):
            raise TypeError("allow_unverified_interruption must be a boolean.")

    def to_dict(self) -> dict[str, Any]:
        """Convert safety configuration to dictionary representation."""
        return {
            "equipment_type": self.equipment_type,
            "rules": [r.to_dict() for r in self.rules],
            "required_signals": list(self.required_signals),
            "max_telemetry_age_seconds": self.max_telemetry_age_seconds,
            "max_signal_discrepancy": dict(self.max_signal_discrepancy),
            "allow_unverified_interruption": self.allow_unverified_interruption,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> EquipmentSafetyConfig:
        """Create safety configuration dynamically from mapping."""
        rules_data = d.get("rules", [])
        rules = tuple(
            r if isinstance(r, EquipmentSafetyRule) else EquipmentSafetyRule.from_dict(r)
            for r in rules_data
        )
        disc_raw = d.get("max_signal_discrepancy", {})
        if isinstance(disc_raw, Mapping):
            disc = tuple((str(k), float(v)) for k, v in disc_raw.items())
        else:
            disc = tuple((str(item[0]), float(item[1])) for item in disc_raw)
        return cls(
            equipment_type=str(d.get("equipment_type", "DEFAULT")),
            rules=rules,
            required_signals=tuple(d.get("required_signals", ("vibration_rms", "temperature_c"))),
            max_telemetry_age_seconds=(
                float(d["max_telemetry_age_seconds"])
                if d.get("max_telemetry_age_seconds") is not None
                else None
            ),
            max_signal_discrepancy=disc,
            allow_unverified_interruption=bool(d.get("allow_unverified_interruption", False)),
        )

    @classmethod
    def from_file(cls, filepath: str | Any) -> EquipmentSafetyConfig:
        """Load equipment safety rules dynamically from external JSON configuration file."""
        import json
        from pathlib import Path

        path = Path(filepath)
        if not path.is_file():
            raise FileNotFoundError(f"Equipment safety config file not found: {filepath}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_file(self, filepath: str | Any) -> None:
        """Export equipment safety rules to external JSON configuration file."""
        import json
        from pathlib import Path

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)


# Default standard industrial equipment safety rules
DEFAULT_SAFETY_RULES = (
    EquipmentSafetyRule(
        rule_id="RULE_MAX_TEMPERATURE",
        signal_name="temperature_c",
        max_value=85.0,
        required=True,
        description="Machine operating temperature must not exceed 85.0°C during active pause.",
    ),
    EquipmentSafetyRule(
        rule_id="RULE_MAX_VIBRATION",
        signal_name="vibration_rms",
        max_value=4.5,
        required=True,
        description="Vibration level must not exceed 4.5 mm/s RMS to prevent dynamic spindle damage.",
    ),
)

DEFAULT_EQUIPMENT_SAFETY_CONFIG = EquipmentSafetyConfig(
    equipment_type="STANDARD_INDUSTRIAL",
    rules=DEFAULT_SAFETY_RULES,
    required_signals=("vibration_rms", "temperature_c"),
    max_telemetry_age_seconds=300.0,
    max_signal_discrepancy=(("vibration_rms", 1.0), ("temperature_c", 5.0)),
    allow_unverified_interruption=False,
)


@dataclass
class MachineTelemetryContext:
    """Genuinely available machine signals, maintenance context, and physical evidence.

    Attributes:
        machine_id: Machine identifier.
        telemetry_signals: Dictionary of primary sensor readings (e.g. temperature, vibration).
        timestamp: Timestamp of the telemetry reading (seconds since epoch or ISO string).
        current_time: Reference time used to verify telemetry freshness (seconds or ISO string).
        maintenance_stage: Work procedure stage (e.g. 'inspection', 'welding', 'spindle_torque').
        is_reversible_stage: Whether the current maintenance stage can be safely paused/reversed.
        redundant_signals: Optional secondary/backup sensor readings for cross-check validation.
        active_hazards: Tuple of reported environmental or equipment hazards.
        lockout_tagout_verified: Optional verified LOTO status.
        metadata: Arbitrary operational metadata.
    """

    machine_id: Any
    telemetry_signals: dict[str, Any] = field(default_factory=dict)
    timestamp: Any | None = None
    current_time: Any | None = None
    maintenance_stage: str | None = None
    is_reversible_stage: bool | None = None
    redundant_signals: dict[str, Any] = field(default_factory=dict)
    active_hazards: tuple[str, ...] = field(default_factory=tuple)
    lockout_tagout_verified: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary representation."""
        return {
            "machine_id": self.machine_id,
            "telemetry_signals": dict(self.telemetry_signals),
            "timestamp": self.timestamp,
            "current_time": self.current_time,
            "maintenance_stage": self.maintenance_stage,
            "is_reversible_stage": self.is_reversible_stage,
            "redundant_signals": dict(self.redundant_signals),
            "active_hazards": list(self.active_hazards),
            "lockout_tagout_verified": self.lockout_tagout_verified,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MachineTelemetryContext:
        """Create MachineTelemetryContext dynamically from mapping."""
        return cls(
            machine_id=data.get("machine_id", "UNKNOWN"),
            telemetry_signals=dict(data.get("telemetry_signals", {})),
            timestamp=data.get("timestamp"),
            current_time=data.get("current_time"),
            maintenance_stage=data.get("maintenance_stage"),
            is_reversible_stage=data.get("is_reversible_stage"),
            redundant_signals=dict(data.get("redundant_signals", {})),
            active_hazards=tuple(data.get("active_hazards", ())),
            lockout_tagout_verified=data.get("lockout_tagout_verified"),
            metadata=dict(data.get("metadata", {})),
        )

    @classmethod
    def from_file(cls, filepath: str | Any) -> MachineTelemetryContext:
        """Load MachineTelemetryContext dynamically from external JSON file."""
        import json
        from pathlib import Path

        path = Path(filepath)
        if not path.is_file():
            raise FileNotFoundError(f"Machine telemetry file not found: {filepath}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_file(self, filepath: str | Any) -> None:
        """Export MachineTelemetryContext to an external JSON file."""
        import json
        from pathlib import Path

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)


@dataclass(frozen=True)
class SafetyAssessmentResult:
    """Structured, auditable result of a data-driven interruptibility safety assessment.

    Attributes:
        outcome: Outcome code ('SAFE_TO_INTERRUPT', 'UNSAFE_TO_INTERRUPT', 'INDETERMINATE').
        is_safe_to_interrupt: Boolean flag (True ONLY if outcome is SAFE_TO_INTERRUPT).
        evidence_used: Dictionary of exact signals and contextual values evaluated.
        missing_inputs: Tuple of required signals or safety inputs that were absent.
        stale_signals: Tuple of signals exceeding the allowable telemetry freshness threshold.
        conflicting_signals: Dictionary describing diverging primary vs redundant sensors.
        evaluated_rules: Tuple of rule IDs checked during assessment.
        violated_rules: Tuple of rule IDs violated.
        uncertainty_factors: Tuple of reasons why certainty could not be established.
        explanation: Plain-English executive summary.
    """

    outcome: str
    is_safe_to_interrupt: bool
    evidence_used: dict[str, Any]
    missing_inputs: tuple[str, ...]
    stale_signals: tuple[str, ...]
    conflicting_signals: dict[str, Any]
    evaluated_rules: tuple[str, ...]
    violated_rules: tuple[str, ...]
    uncertainty_factors: tuple[str, ...]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        """Convert assessment result to dictionary representation."""
        return {
            "outcome": self.outcome,
            "is_safe_to_interrupt": self.is_safe_to_interrupt,
            "evidence_used": dict(self.evidence_used),
            "missing_inputs": list(self.missing_inputs),
            "stale_signals": list(self.stale_signals),
            "conflicting_signals": dict(self.conflicting_signals),
            "evaluated_rules": list(self.evaluated_rules),
            "violated_rules": list(self.violated_rules),
            "uncertainty_factors": list(self.uncertainty_factors),
            "explanation": self.explanation,
        }

    def explain(self) -> str:
        """Executive summary of safety assessment."""
        lines: list[str] = [
            "================================================================================",
            "ForgeGuard Safety Assessment -- Preemption Safety Audit",
            "================================================================================",
            f"Outcome: {self.outcome} | Safe to Interrupt: {self.is_safe_to_interrupt}",
            f"Evaluated Rules: {list(self.evaluated_rules)}",
            f"Violated Rules: {list(self.violated_rules) if self.violated_rules else 'None'}",
            f"Missing Inputs: {list(self.missing_inputs) if self.missing_inputs else 'None'}",
            f"Stale Signals: {list(self.stale_signals) if self.stale_signals else 'None'}",
            f"Conflicting Signals: {self.conflicting_signals if self.conflicting_signals else 'None'}",
            f"Explanation: {self.explanation}",
            "================================================================================",
        ]
        return "\n".join(lines)


def _parse_time(val: Any) -> float | None:
    """Convert timestamp to float seconds if possible."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val) if math.isfinite(val) else None
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            pass
        # Try ISO parsing if available
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            return dt.timestamp()
        except Exception:
            return None
    return None


def assess_job_safety(
    context: MachineTelemetryContext | Mapping[str, Any] | None,
    config: EquipmentSafetyConfig | None = None,
) -> SafetyAssessmentResult:
    """Evaluates whether an active machine maintenance job is safe to interrupt.

    Applies data-driven safety checks against genuinely available signals:
    1. Evaluates presence of all required signals.
    2. Evaluates telemetry freshness against configured age limits.
    3. Cross-checks primary vs redundant sensor signals for conflict.
    4. Evaluates active hazard flags and maintenance stage reversibility.
    5. Evaluates equipment safety rules (e.g. temperature, vibration boundaries).

    Args:
        context: Telemetry and maintenance context for the active machine/job.
        config: EquipmentSafetyConfig containing externalized safety rules and limits.

    Returns:
        SafetyAssessmentResult with outcome SAFE_TO_INTERRUPT, UNSAFE_TO_INTERRUPT,
        or INDETERMINATE, accompanied by full evidence and uncertainty audit.
    """
    from pathlib import Path

    if config is not None:
        if isinstance(config, (str, Path)):
            cfg = EquipmentSafetyConfig.from_file(config)
        elif isinstance(config, Mapping):
            cfg = EquipmentSafetyConfig.from_dict(config)
        elif isinstance(config, EquipmentSafetyConfig):
            cfg = config
        else:
            raise TypeError(
                f"config must be EquipmentSafetyConfig, mapping, or file path, got {type(config).__name__}."
            )
    else:
        cfg = DEFAULT_EQUIPMENT_SAFETY_CONFIG

    # Normalize context into MachineTelemetryContext
    if context is None:
        ctx = MachineTelemetryContext(machine_id="UNKNOWN")
    elif isinstance(context, (str, Path)):
        ctx = MachineTelemetryContext.from_file(context)
    elif isinstance(context, MachineTelemetryContext):
        ctx = context
    elif isinstance(context, Mapping):
        ctx = MachineTelemetryContext.from_dict(context)
    else:
        raise TypeError(
            f"context must be MachineTelemetryContext, mapping, or file path, got {type(context).__name__}."
        )

    evidence_used: dict[str, Any] = {}
    missing_inputs: list[str] = []
    stale_signals: list[str] = []
    conflicting_signals: dict[str, Any] = {}
    evaluated_rules: list[str] = []
    violated_rules: list[str] = []
    uncertainty_factors: list[str] = []

    # 1. Evaluate Required Signals
    for req_sig in cfg.required_signals:
        if req_sig not in ctx.telemetry_signals or ctx.telemetry_signals[req_sig] is None:
            missing_inputs.append(req_sig)
            uncertainty_factors.append(f"Required telemetry signal '{req_sig}' is missing.")
        else:
            evidence_used[req_sig] = ctx.telemetry_signals[req_sig]

    # 2. Evaluate Telemetry Freshness
    t_data = _parse_time(ctx.timestamp)
    t_now = _parse_time(ctx.current_time)

    if cfg.max_telemetry_age_seconds is not None:
        if t_data is None:
            uncertainty_factors.append("Telemetry timestamp missing; data freshness cannot be verified.")
            stale_signals.append("all_signals_missing_timestamp")
        elif t_now is not None:
            age = t_now - t_data
            evidence_used["telemetry_age_seconds"] = age
            if age < 0.0:
                uncertainty_factors.append(
                    f"Telemetry timestamp is in the future (age: {age:.2f}s); clock skew or invalid timestamp."
                )
                stale_signals.append("timestamp_future")
            elif age > cfg.max_telemetry_age_seconds:
                uncertainty_factors.append(
                    f"Telemetry data is stale (age: {age:.1f}s > limit: {cfg.max_telemetry_age_seconds:.1f}s)."
                )
                stale_signals.append("telemetry_age_exceeded")

    # 3. Evaluate Sensor Conflict / Redundancy
    discrepancy_dict = dict(cfg.max_signal_discrepancy)
    for sig_name, secondary_val in ctx.redundant_signals.items():
        if sig_name in ctx.telemetry_signals and secondary_val is not None:
            primary_val = ctx.telemetry_signals[sig_name]
            evidence_used[f"redundant_{sig_name}"] = secondary_val
            try:
                p_num = float(primary_val)
                s_num = float(secondary_val)
                diff = abs(p_num - s_num)
                evidence_used[f"discrepancy_{sig_name}"] = diff
                allowed_diff = discrepancy_dict.get(sig_name, 0.0)
                if diff > allowed_diff:
                    conflicting_signals[sig_name] = {
                        "primary": p_num,
                        "redundant": s_num,
                        "discrepancy": diff,
                        "allowed_limit": allowed_diff,
                    }
                    uncertainty_factors.append(
                        f"Sensor conflict on '{sig_name}': primary={p_num}, redundant={s_num} (diff={diff:.2f} > {allowed_diff:.2f})."
                    )
            except (ValueError, TypeError):
                if primary_val != secondary_val:
                    conflicting_signals[sig_name] = {
                        "primary": primary_val,
                        "redundant": secondary_val,
                    }
                    uncertainty_factors.append(
                        f"Sensor conflict on '{sig_name}': primary='{primary_val}', redundant='{secondary_val}'."
                    )

    # 4. Evaluate Active Hazards
    if ctx.active_hazards:
        evidence_used["active_hazards"] = list(ctx.active_hazards)
        violated_rules.append("RULE_ACTIVE_HAZARDS_PRESENT")
        explanation = (
            f"Machine '{ctx.machine_id}' has active environmental or physical hazards: "
            f"{list(ctx.active_hazards)}. Preemption unsafe."
        )
        return SafetyAssessmentResult(
            outcome=OUTCOME_UNSAFE_TO_INTERRUPT,
            is_safe_to_interrupt=False,
            evidence_used=evidence_used,
            missing_inputs=tuple(missing_inputs),
            stale_signals=tuple(stale_signals),
            conflicting_signals=conflicting_signals,
            evaluated_rules=("RULE_ACTIVE_HAZARDS_PRESENT",),
            violated_rules=tuple(violated_rules),
            uncertainty_factors=tuple(uncertainty_factors),
            explanation=explanation,
        )

    # 5. Evaluate Reversibility of Maintenance Stage
    if ctx.is_reversible_stage is False:
        evidence_used["is_reversible_stage"] = False
        evidence_used["maintenance_stage"] = ctx.maintenance_stage
        violated_rules.append("RULE_IRREVERSIBLE_STAGE")
        explanation = (
            f"Maintenance stage '{ctx.maintenance_stage}' on machine '{ctx.machine_id}' is non-reversible; "
            "job cannot be safely interrupted."
        )
        return SafetyAssessmentResult(
            outcome=OUTCOME_UNSAFE_TO_INTERRUPT,
            is_safe_to_interrupt=False,
            evidence_used=evidence_used,
            missing_inputs=tuple(missing_inputs),
            stale_signals=tuple(stale_signals),
            conflicting_signals=conflicting_signals,
            evaluated_rules=("RULE_IRREVERSIBLE_STAGE",),
            violated_rules=tuple(violated_rules),
            uncertainty_factors=tuple(uncertainty_factors),
            explanation=explanation,
        )

    # 6. Evaluate Configured Equipment Rules
    for rule in cfg.rules:
        evaluated_rules.append(rule.rule_id)
        val = ctx.telemetry_signals.get(rule.signal_name)

        if val is None:
            if rule.required and rule.signal_name not in missing_inputs:
                missing_inputs.append(rule.signal_name)
                uncertainty_factors.append(
                    f"Rule '{rule.rule_id}' requires missing signal '{rule.signal_name}'."
                )
            continue

        evidence_used[rule.signal_name] = val

        # Evaluate numeric boundaries
        try:
            num_val = float(val)
            if rule.max_value is not None and num_val > rule.max_value:
                violated_rules.append(rule.rule_id)
                uncertainty_factors.append(
                    f"Rule '{rule.rule_id}' violated: {rule.signal_name}={num_val} > max_allowed={rule.max_value}."
                )
            if rule.min_value is not None and num_val < rule.min_value:
                violated_rules.append(rule.rule_id)
                uncertainty_factors.append(
                    f"Rule '{rule.rule_id}' violated: {rule.signal_name}={num_val} < min_allowed={rule.min_value}."
                )
        except (ValueError, TypeError):
            # Categorical checks
            pass

        # Evaluate categorical boundaries
        if rule.disallowed_values and val in rule.disallowed_values:
            violated_rules.append(rule.rule_id)
            uncertainty_factors.append(
                f"Rule '{rule.rule_id}' violated: value '{val}' is in disallowed set {rule.disallowed_values}."
            )
        if rule.allowed_values and val not in rule.allowed_values:
            violated_rules.append(rule.rule_id)
            uncertainty_factors.append(
                f"Rule '{rule.rule_id}' violated: value '{val}' is not in permitted set {rule.allowed_values}."
            )

    # 7. Check if any safety rules were violated (UNSAFE outcome)
    if violated_rules:
        explanation = (
            f"Safety assessment failed for machine '{ctx.machine_id}'. Violated rules: {violated_rules}. "
            f"Preemption is unsafe and strictly forbidden."
        )
        return SafetyAssessmentResult(
            outcome=OUTCOME_UNSAFE_TO_INTERRUPT,
            is_safe_to_interrupt=False,
            evidence_used=evidence_used,
            missing_inputs=tuple(missing_inputs),
            stale_signals=tuple(stale_signals),
            conflicting_signals=conflicting_signals,
            evaluated_rules=tuple(evaluated_rules),
            violated_rules=tuple(violated_rules),
            uncertainty_factors=tuple(uncertainty_factors),
            explanation=explanation,
        )

    # 8. Check for missing, stale, or conflicting data (INDETERMINATE outcome)
    if missing_inputs or stale_signals or conflicting_signals:
        if not cfg.allow_unverified_interruption:
            reasons = []
            if missing_inputs:
                reasons.append(f"missing signals {missing_inputs}")
            if stale_signals:
                reasons.append(f"stale telemetry ({stale_signals})")
            if conflicting_signals:
                reasons.append(f"conflicting sensors on {list(conflicting_signals.keys())}")
            reason_str = ", ".join(reasons)

            explanation = (
                f"Interruptibility safety for machine '{ctx.machine_id}' is INDETERMINATE due to {reason_str}. "
                "Automatic preemption is blocked pending manual human/supervisor safety verification."
            )
            return SafetyAssessmentResult(
                outcome=OUTCOME_INDETERMINATE,
                is_safe_to_interrupt=False,
                evidence_used=evidence_used,
                missing_inputs=tuple(missing_inputs),
                stale_signals=tuple(stale_signals),
                conflicting_signals=conflicting_signals,
                evaluated_rules=tuple(evaluated_rules),
                violated_rules=(),
                uncertainty_factors=tuple(uncertainty_factors),
                explanation=explanation,
            )

    # 9. All required evidence verified, fresh, non-conflicting, and within safety limits (SAFE outcome)
    explanation = (
        f"Machine '{ctx.machine_id}' passed all data-driven safety checks ({len(evaluated_rules)} rules evaluated). "
        "Telemetry is fresh, non-conflicting, and operating within safe tolerances. Safe to interrupt."
    )
    return SafetyAssessmentResult(
        outcome=OUTCOME_SAFE_TO_INTERRUPT,
        is_safe_to_interrupt=True,
        evidence_used=evidence_used,
        missing_inputs=(),
        stale_signals=(),
        conflicting_signals={},
        evaluated_rules=tuple(evaluated_rules),
        violated_rules=(),
        uncertainty_factors=(),
        explanation=explanation,
    )
