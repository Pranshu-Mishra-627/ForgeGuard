from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from ml.preprocessing import (
    FAILURE_MODE_COLS,
    REQUIRED_RAW_FEATURES,
    validate_input_features,
)


class ForgeGuardModel:
    def __init__(
        self,
        failure_pipeline: Pipeline,
        mode_pipeline: Pipeline,
        threshold: float = 0.5,
        cost_fn: float = 20.0,
        cost_fp: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.failure_pipeline = failure_pipeline
        self.mode_pipeline = mode_pipeline
        self.threshold = float(threshold)
        self.cost_fn = float(cost_fn)
        self.cost_fp = float(cost_fp)
        self.metadata = metadata or {}

    def predict_failure_proba(self, df: pd.DataFrame) -> np.ndarray:
        valid_df = validate_input_features(df)
        raw_X = valid_df[REQUIRED_RAW_FEATURES]
        probs = self.failure_pipeline.predict_proba(raw_X)
        return probs[:, 1].astype(float)

    def predict_mode_probas(self, df: pd.DataFrame) -> Dict[str, np.ndarray]:
        valid_df = validate_input_features(df)
        raw_X = valid_df[REQUIRED_RAW_FEATURES]
        raw_mode_probs = self.mode_pipeline.predict_proba(raw_X)

        mode_probs: Dict[str, np.ndarray] = {}
        for idx, mode in enumerate(FAILURE_MODE_COLS):
            mode_arr = raw_mode_probs[idx]
            if mode_arr.ndim == 2 and mode_arr.shape[1] > 1:
                mode_probs[mode] = mode_arr[:, 1].astype(float)
            else:
                mode_probs[mode] = mode_arr.ravel().astype(float)
        return mode_probs

    def diagnose_failure_modes(
        self,
        df: pd.DataFrame,
        failure_probs: np.ndarray,
        mode_threshold: float = 0.15,
    ) -> List[str]:
        mode_probs_dict = self.predict_mode_probas(df)
        n_samples = len(df)
        results: List[str] = []

        for i in range(n_samples):
            f_prob = failure_probs[i]
            if f_prob < self.threshold:
                results.append("None")
                continue

            sample_mode_probs = {
                mode: mode_probs_dict[mode][i] for mode in FAILURE_MODE_COLS
            }

            active_modes = [
                mode
                for mode, prob in sample_mode_probs.items()
                if prob >= mode_threshold
            ]

            if active_modes:
                active_modes.sort(key=lambda m: sample_mode_probs[m], reverse=True)
                results.append(", ".join(active_modes))
            else:
                top_mode = max(sample_mode_probs.keys(), key=lambda m: sample_mode_probs[m])
                if sample_mode_probs[top_mode] > 0.05:
                    results.append(top_mode)
                else:
                    results.append("Unspecified Failure")

        return results

    def predict_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        valid_df = validate_input_features(df)

        if "machine_id" in df.columns:
            machine_ids = df["machine_id"].values
        elif "UDI" in df.columns:
            machine_ids = df["UDI"].values
        elif "Product ID" in df.columns:
            machine_ids = df["Product ID"].values
        else:
            machine_ids = [f"M_{idx}" for idx in df.index]

        failure_probs = self.predict_failure_proba(valid_df)
        predicted_modes = self.diagnose_failure_modes(valid_df, failure_probs)

        out_df = pd.DataFrame(
            {
                "machine_id": machine_ids,
                "failure_probability": np.round(failure_probs, 4),
                "predicted_failure_mode": predicted_modes,
                "maintenance_alert": (failure_probs >= self.threshold),
            },
            index=df.index,
        )
        return out_df
