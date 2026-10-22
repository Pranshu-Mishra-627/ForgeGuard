"""Prediction adapter service for Person 1 ML model integration.

Provides single and batch prediction interfaces with validation, stable IDs,
and explicit model metadata. Reuses Person 1's `predict_machines` or registered
callable, strictly preserving model output semantics without inventing formulas
or failure horizons.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from engine.pipeline import resolve_predict_machines

_ACTIVE_PREDICT_FN: Callable[[pd.DataFrame], pd.DataFrame] | None = None
_DEFAULT_MODEL_VERSION: str | None = None


def set_active_predict_fn(
    fn: Callable[[pd.DataFrame], pd.DataFrame] | None,
    model_version: str | None = None,
) -> None:
    """Registers an active ML prediction function and version identifier for the service."""
    global _ACTIVE_PREDICT_FN, _DEFAULT_MODEL_VERSION
    _ACTIVE_PREDICT_FN = fn
    _DEFAULT_MODEL_VERSION = model_version


def get_active_predict_fn() -> Callable[[pd.DataFrame], pd.DataFrame] | None:
    """Returns the currently registered ML prediction function if any."""
    return _ACTIVE_PREDICT_FN


def _get_resolved_predict_fn(
    predict_fn: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
) -> Callable[[pd.DataFrame], pd.DataFrame]:
    """Resolves the prediction callable using explicit param, registered fn, or discovery."""
    if predict_fn is not None:
        return resolve_predict_machines(predict_fn)
    if _ACTIVE_PREDICT_FN is not None:
        return _ACTIVE_PREDICT_FN
    return resolve_predict_machines()


def _validate_machine_reading(reading: Mapping[str, Any], index: int | None = None) -> str:
    """Validates an individual machine reading mapping.

    Returns the extracted machine identifier string.
    Raises ValueError or TypeError if invalid.
    """
    prefix = f"Machine reading at index {index}: " if index is not None else "Machine reading: "
    if not isinstance(reading, Mapping):
        raise TypeError(f"{prefix}Expected a JSON object/mapping, got {type(reading).__name__}.")

    mid = reading.get("machine_id") or reading.get("id") or reading.get("Machine_ID")
    if mid is None or str(mid).strip() == "":
        raise ValueError(f"{prefix}Missing required machine identifier 'machine_id'.")

    # Validate finite numeric sensor readings if provided
    for key, val in reading.items():
        if key in (
            "machine_id",
            "id",
            "Machine_ID",
            "predicted_failure_mode",
            "timestamp",
            "metadata",
            "status",
            "job_type",
            "alert_category",
        ):
            continue
        if isinstance(val, bool):
            continue
        if isinstance(val, (int, float, np.number)):
            if not math.isfinite(val):
                raise ValueError(f"{prefix}Sensor field '{key}' must be finite, got {val}.")
        elif isinstance(val, str) and (
            key.endswith(("_c", "_rms", "_rpm", "_bar", "_hz", "_v", "_a", "_temp", "_vibration"))
            or "temp" in key.lower()
            or "vibr" in key.lower()
            or "pressure" in key.lower()
            or "speed" in key.lower()
        ):
            try:
                num = float(val)
                if not math.isfinite(num):
                    raise ValueError(f"{prefix}Sensor field '{key}' must be finite, got {val}.")
            except ValueError:
                raise ValueError(f"{prefix}Sensor field '{key}' must be numeric, got {val!r}.")

    return str(mid)


def predict_single_machine(
    reading: Mapping[str, Any],
    *,
    predict_fn: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
    model_version: str | None = None,
    prediction_horizon: str | None = None,
) -> dict[str, Any]:
    """Predicts failure probability and failure mode for a single machine reading.

    Args:
        reading: Dictionary containing machine_id and telemetry sensor readings.
        predict_fn: Optional prediction callable. If None, uses registered or discovered model.
        model_version: Optional model version string override.
        prediction_horizon: Optional horizon if defined by the model (defaults to None).

    Returns:
        Structured prediction result dictionary conforming to Interface A.
    """
    mid = _validate_machine_reading(reading)
    batch_res = predict_batch_machines(
        [reading],
        predict_fn=predict_fn,
        model_version=model_version,
        prediction_horizon=prediction_horizon,
    )
    return batch_res[0]


def predict_batch_machines(
    readings: Sequence[Mapping[str, Any]],
    *,
    predict_fn: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
    model_version: str | None = None,
    prediction_horizon: str | None = None,
) -> list[dict[str, Any]]:
    """Generates predictions for a batch of machine readings.

    Args:
        readings: Sequence of machine reading dictionaries.
        predict_fn: Optional prediction callable. If None, uses registered or discovered model.
        model_version: Optional model version string override.
        prediction_horizon: Optional horizon if defined by the model.

    Returns:
        List of structured prediction result dictionaries preserving input order and machine IDs.

    Raises:
        ValueError: If readings list is empty or any reading fails input validation.
        TypeError: If readings is not a sequence or contains invalid types.
        ImportError: If no ML model is available and readings do not contain pre-computed probabilities.
    """
    if not isinstance(readings, (list, tuple)):
        raise TypeError(f"readings must be a list or tuple of records, got {type(readings).__name__}.")

    if len(readings) == 0:
        raise ValueError("readings list cannot be empty.")

    # Validate all readings and extract machine IDs
    machine_ids: list[str] = []
    for idx, r in enumerate(readings):
        mid = _validate_machine_reading(r, index=idx)
        machine_ids.append(mid)

    # Check if a model is available
    resolved_fn: Callable[[pd.DataFrame], pd.DataFrame] | None = None
    try:
        resolved_fn = _get_resolved_predict_fn(predict_fn)
    except ImportError:
        resolved_fn = None

    ts_now = datetime.now(timezone.utc).isoformat()
    version_id = model_version or _DEFAULT_MODEL_VERSION or "ForgeGuard-ML-v1.0"

    # If an ML model is resolved, invoke it
    if resolved_fn is not None:
        input_df = pd.DataFrame(list(readings))
        if "machine_id" not in input_df.columns:
            input_df["machine_id"] = machine_ids

        pred_df = resolved_fn(input_df)

        if "failure_probability" not in pred_df.columns:
            raise ValueError(
                f"Prediction model output missing required 'failure_probability' column: {list(pred_df.columns)}"
            )

        results: list[dict[str, Any]] = []
        for i, row in pred_df.iterrows():
            orig_reading = readings[i] if i < len(readings) else {}
            prob = float(row["failure_probability"])
            if not math.isfinite(prob) or not (0.0 <= prob <= 1.0):
                raise ValueError(f"Machine '{machine_ids[i]}' returned invalid probability: {prob}.")

            mode = str(row.get("predicted_failure_mode", "Unknown"))
            alert = bool(row["maintenance_alert"]) if "maintenance_alert" in row and pd.notna(row["maintenance_alert"]) else None
            record_ts = orig_reading.get("timestamp") or ts_now

            results.append({
                "machine_id": machine_ids[i],
                "failure_probability": prob,
                "predicted_failure_mode": mode,
                "maintenance_alert": alert,
                "prediction_timestamp": str(record_ts),
                "model_version": version_id,
                "prediction_horizon": prediction_horizon,
            })
        return results

    # If no ML model is available, check if pre-computed failure_probability was supplied in readings (e.g. simulation replay)
    has_precomputed = all(
        ("failure_probability" in r or "probability" in r) for r in readings
    )
    if has_precomputed:
        results = []
        for i, r in enumerate(readings):
            raw_prob = r.get("failure_probability", r.get("probability"))
            if raw_prob is None or isinstance(raw_prob, bool) or not isinstance(raw_prob, (int, float, np.number)):
                raise TypeError(f"Machine '{machine_ids[i]}' failure_probability must be numeric.")
            prob = float(raw_prob)
            if not math.isfinite(prob) or not (0.0 <= prob <= 1.0):
                raise ValueError(f"Machine '{machine_ids[i]}' failure_probability out of bounds [0.0, 1.0]: {prob}.")

            mode = str(r.get("predicted_failure_mode", "Unknown"))
            alert = bool(r["maintenance_alert"]) if "maintenance_alert" in r else None
            record_ts = r.get("timestamp") or ts_now

            results.append({
                "machine_id": machine_ids[i],
                "failure_probability": prob,
                "predicted_failure_mode": mode,
                "maintenance_alert": alert,
                "prediction_timestamp": str(record_ts),
                "model_version": version_id,
                "prediction_horizon": prediction_horizon,
            })
        return results

    # No ML model found and readings lack probabilities
    raise ImportError(
        "Person 1's ML prediction function 'predict_machines' was not found, and readings do not contain "
        "pre-computed 'failure_probability'. Please register a model with 'set_active_predict_fn()' or "
        "ensure Person 1's ML module is installed on the Python path."
    )
