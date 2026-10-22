from typing import List
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler

REQUIRED_RAW_FEATURES: List[str] = [
    "Type",
    "Air temperature [K]",
    "Process temperature [K]",
    "Rotational speed [rpm]",
    "Torque [Nm]",
    "Tool wear [min]",
]

ENGINEERED_NUMERIC_FEATURES: List[str] = [
    "Temp difference [K]",
    "Power [W]",
    "Overstrain [min*Nm]",
]

BASE_NUMERIC_FEATURES: List[str] = [
    "Air temperature [K]",
    "Process temperature [K]",
    "Rotational speed [rpm]",
    "Torque [Nm]",
    "Tool wear [min]",
]

ALL_NUMERIC_FEATURES: List[str] = BASE_NUMERIC_FEATURES + ENGINEERED_NUMERIC_FEATURES
CATEGORICAL_FEATURES: List[str] = ["Type"]

FAILURE_TARGET_COL: str = "Machine failure"
FAILURE_MODE_COLS: List[str] = ["TWF", "HDF", "PWF", "OSF", "RNF"]


class DomainFeatureEngineer(BaseEstimator, TransformerMixin):
    def __init__(self) -> None:
        pass

    def fit(self, X: pd.DataFrame, y=None) -> "DomainFeatureEngineer":
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(X, pd.DataFrame):
            raise TypeError(f"Expected pandas DataFrame, got {type(X)}")

        X_out = X.copy()
        air_temp = X_out["Air temperature [K]"].astype(float)
        proc_temp = X_out["Process temperature [K]"].astype(float)
        X_out["Temp difference [K]"] = proc_temp - air_temp

        torque = X_out["Torque [Nm]"].astype(float)
        speed = X_out["Rotational speed [rpm]"].astype(float)
        X_out["Power [W]"] = (torque * speed * 2.0 * np.pi) / 60.0

        tool_wear = X_out["Tool wear [min]"].astype(float)
        X_out["Overstrain [min*Nm]"] = tool_wear * torque
        return X_out


def build_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), ALL_NUMERIC_FEATURES),
            (
                "cat",
                OneHotEncoder(
                    categories=[["L", "M", "H"]],
                    handle_unknown="ignore",
                    sparse_output=False,
                ),
                CATEGORICAL_FEATURES,
            ),
        ],
        remainder="drop",
    )


def validate_input_features(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"predict_machines expects a pandas DataFrame, got {type(df).__name__}")

    if df.empty:
        raise ValueError("Input DataFrame is empty. Provide at least one machine telemetry record.")

    missing_cols = [col for col in REQUIRED_RAW_FEATURES if col not in df.columns]
    if missing_cols:
        raise ValueError(
            f"Missing required telemetry columns: {missing_cols}. Expected all of: {REQUIRED_RAW_FEATURES}"
        )

    for col in BASE_NUMERIC_FEATURES:
        if not pd.api.types.is_numeric_dtype(df[col]):
            try:
                pd.to_numeric(df[col])
            except Exception as e:
                raise ValueError(f"Column '{col}' must contain numeric values. Parse error: {e}")

    null_counts = df[REQUIRED_RAW_FEATURES].isnull().sum()
    cols_with_nulls = null_counts[null_counts > 0].to_dict()
    if cols_with_nulls:
        raise ValueError(
            f"Input features contain missing (NaN) values: {cols_with_nulls}. "
            "All telemetry readings must be valid non-null values."
        )

    return df.copy()
