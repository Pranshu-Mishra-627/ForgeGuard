import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Tuple
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.model import ForgeGuardModel
from ml.preprocessing import (
    DomainFeatureEngineer,
    FAILURE_MODE_COLS,
    FAILURE_TARGET_COL,
    REQUIRED_RAW_FEATURES,
    build_preprocessor,
)


def load_dataset(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Dataset not found at: {csv_path}.\n"
            "Please ensure 'ai4i2020.csv' is placed in 'ml/data/' or specify --data-path."
        )

    df = pd.read_csv(csv_path)
    expected_cols = REQUIRED_RAW_FEATURES + [FAILURE_TARGET_COL] + FAILURE_MODE_COLS
    missing = [c for c in expected_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Dataset at {csv_path} is missing expected columns: {missing}")

    if df[expected_cols].isnull().any().any():
        null_summary = df[expected_cols].isnull().sum().to_dict()
        raise ValueError(f"Dataset contains null values: {null_summary}")

    return df


def optimize_cost_threshold(
    y_true: np.ndarray,
    val_probs: np.ndarray,
    cost_fn: float = 20.0,
    cost_fp: float = 1.0,
) -> Tuple[float, float, List[Dict[str, float]]]:
    threshold_grid = np.linspace(0.02, 0.98, 97)
    best_threshold = 0.5
    min_cost = float("inf")
    curve_data: List[Dict[str, float]] = []

    for t in threshold_grid:
        preds = (val_probs >= t).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_true, preds).ravel()
        cost = float(cost_fn * fn + cost_fp * fp)
        prec = float(precision_score(y_true, preds, zero_division=0))
        rec = float(recall_score(y_true, preds, zero_division=0))
        f1 = float(f1_score(y_true, preds, zero_division=0))

        curve_data.append(
            {
                "threshold": round(float(t), 3),
                "cost": round(cost, 2),
                "false_negatives": int(fn),
                "false_positives": int(fp),
                "true_positives": int(tp),
                "true_negatives": int(tn),
                "precision": round(prec, 4),
                "recall": round(rec, 4),
                "f1_score": round(f1, 4),
            }
        )

        if cost < min_cost:
            min_cost = cost
            best_threshold = float(t)

    return best_threshold, min_cost, curve_data


def train_models(
    data_path: Path,
    output_dir: Path,
    random_state: int = 42,
    cost_fn: float = 20.0,
    cost_fp: float = 1.0,
) -> ForgeGuardModel:
    print("=" * 70)
    print("  FORGEGUARD ML PIPELINE: PS 2.1 MAINTENANCE SHIFT PLANNER")
    print("=" * 70)

    print(f"\n[1/6] Loading dataset from: {data_path}")
    df = load_dataset(data_path)
    n_total = len(df)
    n_failures = int(df[FAILURE_TARGET_COL].sum())
    fail_rate = n_failures / n_total
    print(f"      Loaded {n_total} records. Total failures: {n_failures} ({fail_rate:.2%})")

    print("\n[2/6] Performing stratified train / validation / test split (70 / 15 / 15)...")
    X_raw = df[REQUIRED_RAW_FEATURES].copy()
    y_fail = df[FAILURE_TARGET_COL].values
    Y_modes = df[FAILURE_MODE_COLS].values

    indices = np.arange(len(df))
    idx_train, idx_temp, y_train, y_temp = train_test_split(
        indices, y_fail, test_size=0.30, random_state=random_state, stratify=y_fail
    )
    idx_val, idx_test, y_val, y_test = train_test_split(
        idx_temp, y_temp, test_size=0.50, random_state=random_state, stratify=y_temp
    )

    X_train_df = X_raw.iloc[idx_train]
    X_val_df = X_raw.iloc[idx_val]
    X_test_df = X_raw.iloc[idx_test]

    Y_modes_train = Y_modes[idx_train]
    Y_modes_test = Y_modes[idx_test]

    print(f"      Train set: {len(X_train_df)} samples, {int(y_train.sum())} failures")
    print(f"      Val set:   {len(X_val_df)} samples, {int(y_val.sum())} failures")
    print(f"      Test set:  {len(X_test_df)} samples, {int(y_test.sum())} failures")

    print("\n[3/6] Training baseline Logistic Regression & primary Random Forest...")
    baseline_pipe = Pipeline(
        [
            ("feat_eng", DomainFeatureEngineer()),
            ("preprocessor", build_preprocessor()),
            (
                "clf",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=1000,
                    random_state=random_state,
                ),
            ),
        ]
    )
    baseline_pipe.fit(X_train_df, y_train)
    base_val_probs = baseline_pipe.predict_proba(X_val_df)[:, 1]
    base_val_roc = float(roc_auc_score(y_val, base_val_probs))
    base_val_pr = float(average_precision_score(y_val, base_val_probs))

    rf_pipe = Pipeline(
        [
            ("feat_eng", DomainFeatureEngineer()),
            ("preprocessor", build_preprocessor()),
            (
                "clf",
                RandomForestClassifier(
                    n_estimators=150,
                    max_depth=12,
                    min_samples_split=4,
                    class_weight="balanced",
                    random_state=random_state,
                    n_jobs=-1,
                ),
            ),
        ]
    )
    rf_pipe.fit(X_train_df, y_train)
    rf_val_probs = rf_pipe.predict_proba(X_val_df)[:, 1]
    rf_val_roc = float(roc_auc_score(y_val, rf_val_probs))
    rf_val_pr = float(average_precision_score(y_val, rf_val_probs))

    print(f"      Baseline (Logistic Regression) Val ROC-AUC: {base_val_roc:.4f} | PR-AUC: {base_val_pr:.4f}")
    print(f"      Primary (Random Forest)        Val ROC-AUC: {rf_val_roc:.4f} | PR-AUC: {rf_val_pr:.4f}")

    print(f"\n[4/6] Optimizing decision threshold using cost model (Cost: FN={cost_fn}x, FP={cost_fp}x)...")
    best_thresh, min_val_cost, cost_curve = optimize_cost_threshold(
        y_val, rf_val_probs, cost_fn=cost_fn, cost_fp=cost_fp
    )
    
    default_preds = (rf_val_probs >= 0.5).astype(int)
    tn_def, fp_def, fn_def, tp_def = confusion_matrix(y_val, default_preds).ravel()
    default_val_cost = float(cost_fn * fn_def + cost_fp * fp_def)

    print(f"      Default Threshold (0.50): Cost={default_val_cost:.1f} (FN={fn_def}, FP={fp_def})")
    print(f"      Optimal Threshold ({best_thresh:.3f}): Cost={min_val_cost:.1f} "
          f"({((default_val_cost - min_val_cost)/default_val_cost):.1%} cost reduction)")

    print("\n[5/6] Training multi-output failure-mode diagnoser (TWF, HDF, PWF, OSF, RNF)...")
    mode_pipe = Pipeline(
        [
            ("feat_eng", DomainFeatureEngineer()),
            ("preprocessor", build_preprocessor()),
            (
                "clf",
                RandomForestClassifier(
                    n_estimators=100,
                    class_weight="balanced",
                    random_state=random_state,
                    n_jobs=-1,
                ),
            ),
        ]
    )
    mode_pipe.fit(X_train_df, Y_modes_train)

    print("\n[6/6] Evaluating final model on PRESERVED HELD-OUT TEST SET...")
    test_probs = rf_pipe.predict_proba(X_test_df)[:, 1]
    test_roc_auc = float(roc_auc_score(y_test, test_probs))
    test_pr_auc = float(average_precision_score(y_test, test_probs))

    test_preds_opt = (test_probs >= best_thresh).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test, test_preds_opt).ravel()
    test_cost_opt = float(cost_fn * fn + cost_fp * fp)
    test_precision = float(precision_score(y_test, test_preds_opt, zero_division=0))
    test_recall = float(recall_score(y_test, test_preds_opt, zero_division=0))
    test_f1 = float(f1_score(y_test, test_preds_opt, zero_division=0))

    test_preds_def = (test_probs >= 0.50).astype(int)
    tn_d, fp_d, fn_d, tp_d = confusion_matrix(y_test, test_preds_def).ravel()
    test_cost_def = float(cost_fn * fn_d + cost_fp * fp_d)

    print("      " + "-" * 50)
    print(f"      TEST ROC-AUC:         {test_roc_auc:.4f}")
    print(f"      TEST PR-AUC:          {test_pr_auc:.4f}")
    print(f"      TEST PRECISION:       {test_precision:.4f} (at threshold {best_thresh:.3f})")
    print(f"      TEST RECALL:          {test_recall:.4f} ({tp}/{tp+fn} failures caught)")
    print(f"      TEST F1-SCORE:        {test_f1:.4f}")
    print(f"      TEST COST (Optimal):  {test_cost_opt:.1f} (FN={fn}, FP={fp})")
    print(f"      TEST COST (Default):  {test_cost_def:.1f} (FN={fn_d}, FP={fp_d})")
    print(f"      CONFUSION MATRIX:     [[TN={tn}, FP={fp}], [FN={fn}, TP={tp}]]")
    print("      " + "-" * 50)

    raw_mode_test_probs = mode_pipe.predict_proba(X_test_df)
    mode_test_metrics = {}
    for i, mode_name in enumerate(FAILURE_MODE_COLS):
        mode_arr = raw_mode_test_probs[i]
        mode_p = mode_arr[:, 1] if (mode_arr.ndim == 2 and mode_arr.shape[1] > 1) else mode_arr.ravel()
        m_pred = (mode_p >= 0.20).astype(int)
        m_true = Y_modes_test[:, i]
        mode_test_metrics[mode_name] = {
            "support": int(m_true.sum()),
            "precision": round(float(precision_score(m_true, m_pred, zero_division=0)), 4),
            "recall": round(float(recall_score(m_true, m_pred, zero_division=0)), 4),
            "f1": round(float(f1_score(m_true, m_pred, zero_division=0)), 4),
        }
        print(f"      Mode {mode_name:4s}: Support={m_true.sum():2d} | "
              f"Precision={mode_test_metrics[mode_name]['precision']:.2f} | "
              f"Recall={mode_test_metrics[mode_name]['recall']:.2f} | "
              f"F1={mode_test_metrics[mode_name]['f1']:.2f}")

    rf_clf = rf_pipe.named_steps["clf"]
    prep_step = rf_pipe.named_steps["preprocessor"]
    transformed_feature_names = [
        f.replace("num__", "").replace("cat__", "")
        for f in prep_step.get_feature_names_out()
    ]
    raw_importances = rf_clf.feature_importances_
    sorted_importances = sorted(
        [
            {"feature": name, "importance": round(float(imp), 4)}
            for name, imp in zip(transformed_feature_names, raw_importances)
        ],
        key=lambda x: x["importance"],
        reverse=True,
    )

    model = ForgeGuardModel(
        failure_pipeline=rf_pipe,
        mode_pipeline=mode_pipe,
        threshold=best_thresh,
        cost_fn=cost_fn,
        cost_fp=cost_fp,
        metadata={
            "model_type": "RandomForestClassifier",
            "random_state": random_state,
            "cost_fn": cost_fn,
            "cost_fp": cost_fp,
            "optimal_threshold": round(best_thresh, 4),
            "test_roc_auc": round(test_roc_auc, 4),
            "test_pr_auc": round(test_pr_auc, 4),
            "test_precision": round(test_precision, 4),
            "test_recall": round(test_recall, 4),
            "test_f1": round(test_f1, 4),
        },
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    model_artifact_path = output_dir / "model.joblib"
    metadata_artifact_path = output_dir / "metadata.json"

    print(f"\n[Saving Artifacts]")
    print(f"      Saving fitted model to:    {model_artifact_path}")
    joblib.dump(model, model_artifact_path, compress=3)

    metadata = {
        "project": "ForgeGuard",
        "problem_statement": "PS 2.1: Maintenance Shift Planner",
        "dataset": {
            "name": "AI4I 2020 Predictive Maintenance Dataset",
            "source": "UCI Machine Learning Repository",
            "url": "https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset",
            "total_samples": n_total,
            "total_failures": n_failures,
            "failure_rate": round(fail_rate, 4),
            "class_imbalance_ratio": round((n_total - n_failures) / n_failures, 2),
            "features_raw": REQUIRED_RAW_FEATURES,
            "features_engineered": [
                "Temp difference [K]",
                "Power [W]",
                "Overstrain [min*Nm]",
            ],
            "excluded_columns": ["UDI", "Product ID", "Target leakage columns"],
            "synthetic_data_disclosure": (
                "AI4I 2020 is a synthetic benchmark dataset generated from physical machine models. "
                "While sensor dynamics reflect real physical relationships, performance on synthetic "
                "telemetry does not guarantee identical real-world industrial plant performance."
            ),
        },
        "training_configuration": {
            "random_seed": random_state,
            "splits": {"train": len(X_train_df), "val": len(X_val_df), "test": len(X_test_df)},
            "stratified_by": FAILURE_TARGET_COL,
            "cost_model": {
                "cost_false_negative": cost_fn,
                "cost_false_positive": cost_fp,
                "ratio": cost_fn / cost_fp,
            },
        },
        "model_comparison": {
            "baseline_logistic_regression": {
                "val_roc_auc": round(base_val_roc, 4),
                "val_pr_auc": round(base_val_pr, 4),
            },
            "primary_random_forest": {
                "val_roc_auc": round(rf_val_roc, 4),
                "val_pr_auc": round(rf_val_pr, 4),
            },
        },
        "threshold_selection": {
            "method": "Validation Cost Curve Minimization",
            "cost_optimal_threshold": round(best_thresh, 4),
            "validation_optimal_cost": round(min_val_cost, 2),
            "validation_default_cost": round(default_val_cost, 2),
            "validation_cost_reduction_pct": round(
                ((default_val_cost - min_val_cost) / default_val_cost) * 100.0, 2
            ),
        },
        "held_out_test_evaluation": {
            "roc_auc": round(test_roc_auc, 4),
            "pr_auc": round(test_pr_auc, 4),
            "at_optimal_threshold": {
                "threshold": round(best_thresh, 4),
                "precision": round(test_precision, 4),
                "recall": round(test_recall, 4),
                "f1_score": round(test_f1, 4),
                "confusion_matrix": {
                    "tn": int(tn),
                    "fp": int(fp),
                    "fn": int(fn),
                    "tp": int(tp),
                },
                "total_cost": round(test_cost_opt, 2),
            },
            "at_default_threshold": {
                "threshold": 0.50,
                "confusion_matrix": {
                    "tn": int(tn_d),
                    "fp": int(fp_d),
                    "fn": int(fn_d),
                    "tp": int(tp_d),
                },
                "total_cost": round(test_cost_def, 2),
            },
            "failure_mode_diagnostics": mode_test_metrics,
        },
        "global_feature_importances": sorted_importances,
        "known_limitations": [
            "AI4I 2020 dataset is synthetic; field telemetry requires calibration.",
            "RNF (Random Failures) is inherently unpredictable (random noise injection in AI4I).",
            "TWF (Tool Wear Failure) has limited positive support (under 50 total samples in dataset).",
            "Failure modes can overlap: multiple modes may be triggered simultaneously on high-stress machines.",
        ],
    }

    print(f"      Saving metadata to:        {metadata_artifact_path}")
    with open(metadata_artifact_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print("\n[DONE] Model artifacts successfully trained and saved!")
    return model


def main() -> None:
    parser = argparse.ArgumentParser(description="Train ForgeGuard predictive maintenance models.")
    parser.add_argument(
        "--data-path",
        type=Path,
        default=REPO_ROOT / "ml" / "data" / "ai4i2020.csv",
        help="Path to AI4I 2020 CSV dataset.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "ml" / "artifacts",
        help="Directory to save trained model artifacts.",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Fixed random seed for reproducibility.",
    )
    parser.add_argument(
        "--cost-fn",
        type=float,
        default=20.0,
        help="Cost multiplier for missed failure (False Negative).",
    )
    parser.add_argument(
        "--cost-fp",
        type=float,
        default=1.0,
        help="Cost multiplier for false alarm inspection (False Positive).",
    )

    args = parser.parse_args()
    train_models(
        data_path=args.data_path,
        output_dir=args.output_dir,
        random_state=args.random_state,
        cost_fn=args.cost_fn,
        cost_fp=args.cost_fp,
    )


if __name__ == "__main__":
    main()
