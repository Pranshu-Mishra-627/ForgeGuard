from pathlib import Path
import json
import sys
from typing import Any, Dict, Optional, Union
import joblib
import numpy as np
import pandas as pd

PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.model import ForgeGuardModel

DEFAULT_ARTIFACTS_DIR = PKG_DIR / "artifacts"
DEFAULT_MODEL_PATH = DEFAULT_ARTIFACTS_DIR / "model.joblib"
DEFAULT_METADATA_PATH = DEFAULT_ARTIFACTS_DIR / "metadata.json"

_CACHED_MODEL: Optional[ForgeGuardModel] = None


def load_model(model_path: Optional[Union[str, Path]] = None, reload: bool = False) -> ForgeGuardModel:
    global _CACHED_MODEL

    target_path = Path(model_path) if model_path is not None else DEFAULT_MODEL_PATH

    if _CACHED_MODEL is not None and not reload and model_path is None:
        return _CACHED_MODEL

    if not target_path.exists():
        raise FileNotFoundError(
            f"ForgeGuard model artifact not found at: {target_path}. "
            "Please run 'python ml/train.py' first to train and generate the model artifact."
        )

    try:
        model = joblib.load(target_path)
    except Exception as e:
        raise RuntimeError(f"Failed to load ForgeGuard model from {target_path}: {e}")

    if model_path is None:
        _CACHED_MODEL = model

    return model


def predict_machines(df: pd.DataFrame, model_path: Optional[Union[str, Path]] = None) -> pd.DataFrame:
    model = load_model(model_path=model_path)
    return model.predict_batch(df)


def predict_single_machine(
    reading: Dict[str, Any],
    machine_id: Optional[str] = None,
    model_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    df = pd.DataFrame([reading])
    if machine_id is not None:
        df["machine_id"] = machine_id

    result_df = predict_machines(df, model_path=model_path)
    return result_df.iloc[0].to_dict()


def get_model_metadata(metadata_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    path = Path(metadata_path) if metadata_path is not None else DEFAULT_METADATA_PATH
    if not path.exists():
        raise FileNotFoundError(f"Metadata artifact not found at {path}")
    with open(path, "r") as f:
        return json.load(f)


def explain_machine(
    reading: Dict[str, Any],
    machine_id: Optional[str] = None,
    model_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    pred = predict_single_machine(reading, machine_id=machine_id, model_path=model_path)

    air_temp = float(reading.get("Air temperature [K]", 300.0))
    proc_temp = float(reading.get("Process temperature [K]", 310.0))
    speed = float(reading.get("Rotational speed [rpm]", 1500.0))
    torque = float(reading.get("Torque [Nm]", 40.0))
    wear = float(reading.get("Tool wear [min]", 0.0))
    m_type = str(reading.get("Type", "L")).upper()

    temp_diff = proc_temp - air_temp
    power_w = (torque * speed * 2.0 * np.pi) / 60.0
    overstrain = wear * torque
    overstrain_limit = {"L": 11000.0, "M": 12000.0, "H": 13000.0}.get(m_type, 11000.0)

    risk_factors = []

    if power_w > 9000.0:
        risk_factors.append(
            {
                "factor": "Excess Power Load (PWF)",
                "observed_value": f"{power_w:.0f} W",
                "normal_range": "3,500 - 9,000 W",
                "severity": "CRITICAL",
                "description": "Mechanical power exceeds 9,000 W maximum motor rating.",
            }
        )
    elif power_w < 3500.0:
        risk_factors.append(
            {
                "factor": "Insufficient Power / Stall (PWF)",
                "observed_value": f"{power_w:.0f} W",
                "normal_range": "3,500 - 9,000 W",
                "severity": "CRITICAL",
                "description": "Power drawn is under 3,500 W indicating stall or drive malfunction.",
            }
        )

    if overstrain >= overstrain_limit:
        risk_factors.append(
            {
                "factor": "Mechanical Overstrain (OSF)",
                "observed_value": f"{overstrain:.0f} min*Nm",
                "normal_range": f"< {overstrain_limit:.0f} min*Nm",
                "severity": "CRITICAL",
                "description": f"Tool wear and torque combination exceeds {m_type}-grade structural limit.",
            }
        )
    elif overstrain >= 0.85 * overstrain_limit:
        risk_factors.append(
            {
                "factor": "Elevated Overstrain (OSF Risk)",
                "observed_value": f"{overstrain:.0f} min*Nm",
                "normal_range": f"< {overstrain_limit:.0f} min*Nm",
                "severity": "WARNING",
                "description": "Approaching mechanical fatigue overstrain threshold.",
            }
        )

    if temp_diff < 8.6 and speed < 1380.0:
        risk_factors.append(
            {
                "factor": "Heat Dissipation Failure (HDF)",
                "observed_value": f"ΔT = {temp_diff:.1f} K, Speed = {speed:.0f} rpm",
                "normal_range": "ΔT >= 8.6 K or Speed >= 1,380 rpm",
                "severity": "CRITICAL",
                "description": "Insufficient convective cooling airflow at low rotational speed.",
            }
        )

    if wear >= 200.0:
        risk_factors.append(
            {
                "factor": "Tool Wear Exhaustion (TWF)",
                "observed_value": f"{wear:.0f} min",
                "normal_range": "< 200 min",
                "severity": "CRITICAL" if wear >= 220 else "WARNING",
                "description": "Tool has exceeded the recommended 200-minute service lifecycle.",
            }
        )

    if not risk_factors and pred["failure_probability"] < 0.20:
        recommended_action = "Nominal operation: No technician intervention required this shift."
    else:
        critical_modes = [rf["factor"].split(" (")[0] for rf in risk_factors if rf["severity"] == "CRITICAL"]
        if critical_modes:
            recommended_action = f"Immediate technician assignment: Inspect {', '.join(critical_modes)}."
        else:
            recommended_action = "Schedule preventive technician inspection during current shift."

    return {
        **pred,
        "recommended_action": recommended_action,
        "telemetry_metrics": {
            "temp_difference_K": round(temp_diff, 2),
            "mechanical_power_W": round(power_w, 1),
            "overstrain_min_Nm": round(overstrain, 1),
        },
        "risk_factors": risk_factors,
    }
