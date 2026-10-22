import json
import os
import shutil
import tempfile
import numpy as np
import pandas as pd
import pytest

from ml.model import ForgeGuardModel
from ml.predict import (
    DEFAULT_METADATA_PATH,
    DEFAULT_MODEL_PATH,
    explain_machine,
    get_model_metadata,
    load_model,
    predict_machines,
    predict_single_machine,
)
from ml.preprocessing import (
    REQUIRED_RAW_FEATURES,
    DomainFeatureEngineer,
)
from ml.train import optimize_cost_threshold


@pytest.fixture
def synthetic_sample_reading():
    return {
        "Type": "M",
        "Air temperature [K]": 300.0,
        "Process temperature [K]": 310.0,
        "Rotational speed [rpm]": 1500,
        "Torque [Nm]": 40.0,
        "Tool wear [min]": 100,
    }


@pytest.fixture
def synthetic_batch_df():
    return pd.DataFrame(
        [
            {
                "machine_id": "M_NORMAL_1",
                "Type": "L",
                "Air temperature [K]": 298.1,
                "Process temperature [K]": 308.6,
                "Rotational speed [rpm]": 1551,
                "Torque [Nm]": 42.8,
                "Tool wear [min]": 5,
            },
            {
                "machine_id": "M_HEAT_STRESS",
                "Type": "H",
                "Air temperature [K]": 304.0,
                "Process temperature [K]": 313.5,
                "Rotational speed [rpm]": 1380,
                "Torque [Nm]": 55.0,
                "Tool wear [min]": 210,
            },
            {
                "machine_id": "M_POWER_STRESS",
                "Type": "L",
                "Air temperature [K]": 299.0,
                "Process temperature [K]": 309.0,
                "Rotational speed [rpm]": 2800,
                "Torque [Nm]": 75.0,
                "Tool wear [min]": 220,
            },
            {
                "machine_id": "M_NORMAL_2",
                "Type": "M",
                "Air temperature [K]": 298.5,
                "Process temperature [K]": 308.7,
                "Rotational speed [rpm]": 1400,
                "Torque [Nm]": 45.0,
                "Tool wear [min]": 12,
            },
        ]
    )


class TestArtifactsAndMetadata:
    def test_artifacts_exist(self):
        assert DEFAULT_MODEL_PATH.exists()
        assert DEFAULT_METADATA_PATH.exists()
        assert DEFAULT_MODEL_PATH.stat().st_size > 1000
        assert DEFAULT_METADATA_PATH.stat().st_size > 100

    def test_metadata_schema_and_contents(self):
        with open(DEFAULT_METADATA_PATH, "r") as f:
            meta = json.load(f)

        assert meta["project"] == "ForgeGuard"
        assert "dataset" in meta
        assert "training_configuration" in meta
        assert "model_comparison" in meta
        assert "threshold_selection" in meta
        assert "held_out_test_evaluation" in meta
        assert "known_limitations" in meta

        test_eval = meta["held_out_test_evaluation"]
        assert test_eval["roc_auc"] >= 0.90
        assert test_eval["pr_auc"] >= 0.70

        opt_metrics = test_eval["at_optimal_threshold"]
        assert 0.0 < opt_metrics["threshold"] < 1.0
        assert 0.0 <= opt_metrics["recall"] <= 1.0
        assert 0.0 <= opt_metrics["precision"] <= 1.0
        assert "confusion_matrix" in opt_metrics


class TestPredictionInterface:
    def test_predict_output_schema(self, synthetic_batch_df):
        res = predict_machines(synthetic_batch_df)
        assert isinstance(res, pd.DataFrame)
        assert len(res) == len(synthetic_batch_df)
        assert "machine_id" in res.columns
        assert "failure_probability" in res.columns
        assert "predicted_failure_mode" in res.columns

    def test_probability_bounds_and_numeric_types(self, synthetic_batch_df):
        res = predict_machines(synthetic_batch_df)
        probs = res["failure_probability"]
        assert pd.api.types.is_numeric_dtype(probs)
        assert not probs.isnull().any()
        assert (probs >= 0.0).all()
        assert (probs <= 1.0).all()

    def test_batch_prediction_and_row_order_preservation(self, synthetic_batch_df):
        res = predict_machines(synthetic_batch_df)
        expected_ids = synthetic_batch_df["machine_id"].tolist()
        actual_ids = res["machine_id"].tolist()
        assert actual_ids == expected_ids

    def test_generated_machine_ids_when_not_provided(self, synthetic_batch_df):
        df_no_ids = synthetic_batch_df.drop(columns=["machine_id"])
        res = predict_machines(df_no_ids)
        assert "machine_id" in res.columns
        assert len(res["machine_id"]) == len(df_no_ids)
        assert len(res["machine_id"].unique()) == len(df_no_ids)

    def test_inference_without_target_columns(self, synthetic_batch_df):
        clean_df = synthetic_batch_df[REQUIRED_RAW_FEATURES].copy()
        res = predict_machines(clean_df)
        assert len(res) == len(clean_df)
        assert (res["failure_probability"] >= 0.0).all()

    def test_missing_required_features_raises_error(self, synthetic_batch_df):
        df_missing = synthetic_batch_df.drop(columns=["Torque [Nm]"])
        with pytest.raises(ValueError, match="Missing required telemetry columns"):
            predict_machines(df_missing)

    def test_empty_dataframe_raises_error(self):
        empty_df = pd.DataFrame(columns=REQUIRED_RAW_FEATURES)
        with pytest.raises(ValueError, match="empty"):
            predict_machines(empty_df)

    def test_invalid_input_type_raises_error(self):
        with pytest.raises(TypeError, match="pandas DataFrame"):
            predict_machines({"Type": "L"})  # type: ignore

    def test_predict_single_machine(self, synthetic_sample_reading):
        res = predict_single_machine(synthetic_sample_reading, machine_id="MACHINE_999")
        assert isinstance(res, dict)
        assert res["machine_id"] == "MACHINE_999"
        assert 0.0 <= res["failure_probability"] <= 1.0
        assert isinstance(res["predicted_failure_mode"], str)
        assert "maintenance_alert" in res

    def test_explain_machine_diagnostics(self, synthetic_sample_reading):
        res = explain_machine(synthetic_sample_reading, machine_id="EXPLAIN_1")
        assert isinstance(res, dict)
        assert res["machine_id"] == "EXPLAIN_1"
        assert "recommended_action" in res
        assert "telemetry_metrics" in res
        assert "risk_factors" in res
        assert "temp_difference_K" in res["telemetry_metrics"]
        assert "mechanical_power_W" in res["telemetry_metrics"]
        assert "overstrain_min_Nm" in res["telemetry_metrics"]

    def test_get_model_metadata(self):
        meta = get_model_metadata()
        assert isinstance(meta, dict)
        assert meta["project"] == "ForgeGuard"
        assert "global_feature_importances" in meta
        assert len(meta["global_feature_importances"]) > 0


class TestFailureModeAndCostBehavior:
    def test_failure_mode_output_behavior(self, synthetic_batch_df):
        res = predict_machines(synthetic_batch_df)
        for _, row in res.iterrows():
            prob = row["failure_probability"]
            mode = row["predicted_failure_mode"]
            if prob < 0.20:
                assert mode == "None"
            else:
                assert mode != ""

    def test_high_stress_machine_diagnoses_overstrain_or_power(self):
        high_stress_df = pd.DataFrame(
            [
                {
                    "machine_id": "CRITICAL_FAIL",
                    "Type": "L",
                    "Air temperature [K]": 299.0,
                    "Process temperature [K]": 309.0,
                    "Rotational speed [rpm]": 2850,
                    "Torque [Nm]": 76.0,
                    "Tool wear [min]": 240,
                }
            ]
        )
        res = predict_machines(high_stress_df)
        assert res.iloc[0]["failure_probability"] >= 0.70
        assert bool(res.iloc[0]["maintenance_alert"]) is True
        predicted_mode = res.iloc[0]["predicted_failure_mode"]
        assert any(mode in predicted_mode for mode in ["OSF", "PWF", "TWF"])

    def test_cost_threshold_optimization_reduces_cost(self):
        y_true = np.array([0] * 90 + [1] * 10)
        val_probs = np.array([0.05] * 80 + [0.35] * 10 + [0.45] * 5 + [0.85] * 5)
        thresh, min_cost, curve = optimize_cost_threshold(y_true, val_probs, cost_fn=20.0, cost_fp=1.0)
        assert 0.0 < thresh < 1.0
        assert len(curve) > 50
        assert min_cost >= 0.0


class TestEnvironmentAndReproducibility:
    def test_model_loading_from_different_working_directory(self, synthetic_batch_df):
        original_cwd = os.getcwd()
        tmp_dir = tempfile.mkdtemp()
        try:
            os.chdir(tmp_dir)
            model = load_model(reload=True)
            res = model.predict_batch(synthetic_batch_df)
            assert len(res) == len(synthetic_batch_df)
            assert (res["failure_probability"] >= 0.0).all()
        finally:
            os.chdir(original_cwd)
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

    def test_reproducible_preprocessing_transform(self, synthetic_batch_df):
        fe = DomainFeatureEngineer()
        df1 = fe.transform(synthetic_batch_df)
        df2 = fe.transform(synthetic_batch_df)
        pd.testing.assert_frame_equal(df1, df2)

        expected_temp_diff = synthetic_batch_df["Process temperature [K]"] - synthetic_batch_df["Air temperature [K]"]
        np.testing.assert_allclose(df1["Temp difference [K]"].values, expected_temp_diff.values)
