"""Claims fraud model: gradient-boosted trees on fraud_features.claim_features.

    uv run fraud-train-claims

Steps:
  1. Rebuild fraud_features.claim_features (models/sql/claim_features.sql).
  2. Cross-validate grouped by agent_id, so every score comes from a model that
     never saw that agent's claims (out-of-fold scores).
  3. Report against the rules baseline and per fraud type.
  4. Write out-of-fold scores to fraud_features.claim_model_scores.
  5. Fit on all data and save to models/artifacts/claims_model.joblib.
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from google.cloud import bigquery
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold

from fraud_agent.config import DATASET_CLEAN, DATASET_FEATURES, get_settings

FEATURES_SQL = Path(__file__).parent / "sql" / "claim_features.sql"
ARTIFACT_DIR = Path(__file__).parent / "artifacts"
MODEL_VERSION = "claims-hgb-v1"

ID_COLUMNS = ["claim_id", "agent_id", "customer_id", "policy_id"]
CATEGORICAL = ["claim_type", "policy_type", "channel", "state"]
N_FOLDS = 5
SEED = 42


def load_data(client: bigquery.Client) -> pd.DataFrame:
    client.query(FEATURES_SQL.read_text()).result()
    return client.query(f"""
        SELECT f.*, c.fraud_flag, c.fraud_type, s.rule_score
        FROM {DATASET_FEATURES}.claim_features f
        JOIN {DATASET_CLEAN}.claims c USING (claim_id)
        JOIN {DATASET_FEATURES}.rule_scores s
          ON s.record_table = 'claims' AND s.record_id = f.claim_id
        ORDER BY claim_id
    """).to_dataframe(create_bqstorage_client=False)


def feature_frame(df: pd.DataFrame, categories: dict[str, list[str]]) -> pd.DataFrame:
    X = df.drop(columns=ID_COLUMNS + ["fraud_flag", "fraud_type", "rule_score"])
    for col in CATEGORICAL:
        X[col] = pd.Categorical(X[col], categories=categories[col])
    return X.astype({c: "float64" for c in X.columns if c not in CATEGORICAL})


def new_model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        learning_rate=0.05,
        max_iter=200,
        max_leaf_nodes=15,
        min_samples_leaf=20,
        l2_regularization=1.0,
        categorical_features="from_dtype",
        early_stopping=False,
        random_state=SEED,
    )


def cross_validate(X: pd.DataFrame, y: np.ndarray, groups: pd.Series):
    oof = np.zeros(len(y))
    importances = []
    cv = StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
    for train_idx, test_idx in cv.split(X, y, groups):
        model = new_model().fit(X.iloc[train_idx], y[train_idx])
        oof[test_idx] = model.predict_proba(X.iloc[test_idx])[:, 1]
        imp = permutation_importance(
            model, X.iloc[test_idx], y[test_idx],
            scoring="average_precision", n_repeats=5, random_state=SEED,
        )
        importances.append(imp.importances_mean)
    return oof, pd.Series(np.mean(importances, axis=0), index=X.columns)


def threshold_for_precision(y: np.ndarray, score: np.ndarray, target: float) -> float | None:
    """Lowest threshold whose precision is >= target (maximises recall)."""
    precision, _, thresholds = precision_recall_curve(y, score)
    ok = np.where(precision[:-1] >= target)[0]
    return float(thresholds[ok[0]]) if len(ok) else None


def _pr(y: np.ndarray, flagged: np.ndarray) -> tuple[int, float, float]:
    tp = int((flagged & (y == 1)).sum())
    n = int(flagged.sum())
    return n, (tp / n if n else 0.0), tp / int(y.sum())


def report(df: pd.DataFrame, y: np.ndarray, oof: np.ndarray, importance: pd.Series) -> dict:
    critical = (df.rule_score >= 1.0).to_numpy()
    rules_any = (df.rule_score > 0).to_numpy()

    print(f"\nOut-of-fold, {N_FOLDS} folds grouped by agent ({int(y.sum())} fraud / {len(y)} claims)")
    print(f"  model PR-AUC {average_precision_score(y, oof):.3f}   ROC-AUC {roc_auc_score(y, oof):.3f}")
    print(f"  rules PR-AUC {average_precision_score(y, df.rule_score):.3f}   "
          f"(base rate {y.mean():.3f})")

    print(f"\n  {'strategy':<44}{'flagged':>8}{'precision':>11}{'recall':>9}")
    rows = [("rules: critical only", critical), ("rules: any hit", rules_any)]
    chosen = {}
    for target in (0.9, 0.8, 0.6):
        t = threshold_for_precision(y, oof, target)
        if t is None:
            continue
        chosen[target] = t
        rows.append((f"model >= {t:.3f} (precision target {target:.0%})", oof >= t))
        rows.append((f"critical rule OR model >= {t:.3f}", critical | (oof >= t)))
    for name, flagged in rows:
        n, p, r = _pr(y, flagged)
        print(f"  {name:<44}{n:>8}{p:>10.1%}{r:>9.1%}")

    if 0.8 in chosen:
        flagged = critical | (oof >= chosen[0.8])
        print(f"\nRecall per fraud type: critical rule OR model >= {chosen[0.8]:.3f}")
        by_type = (
            pd.DataFrame({"fraud_type": df.fraud_type, "caught": flagged})[y == 1]
            .groupby("fraud_type").caught.agg(["size", "mean"])
            .sort_values("size", ascending=False)
        )
        for ft, row in by_type.iterrows():
            print(f"  {ft:<32}{int(row['size']):>4}{row['mean']:>9.1%}")

    print("\nTop features (permutation importance, drop in PR-AUC on held-out folds)")
    for name, value in importance.sort_values(ascending=False).head(10).items():
        print(f"  {name:<32}{value:>8.3f}")

    return {
        "pr_auc": float(average_precision_score(y, oof)),
        "roc_auc": float(roc_auc_score(y, oof)),
        "thresholds": {str(k): v for k, v in chosen.items()},
    }


def write_scores(client: bigquery.Client, df: pd.DataFrame, oof: np.ndarray) -> None:
    out = pd.DataFrame({
        "claim_id": df.claim_id,
        "model_score": oof,
        "model_version": MODEL_VERSION,
        "scored_at": pd.Timestamp(datetime.now(timezone.utc)),
    })
    table = f"{client.project}.{DATASET_FEATURES}.claim_model_scores"
    job = client.load_table_from_dataframe(
        out, table,
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
    )
    job.result()
    print(f"\nWrote {DATASET_FEATURES}.claim_model_scores ({len(out)} rows, out-of-fold)")


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", default=settings.project_id)
    parser.add_argument("--location", default=settings.location)
    args = parser.parse_args()

    client = bigquery.Client(project=args.project, location=args.location)
    df = load_data(client)
    categories = {c: sorted(df[c].dropna().unique().tolist()) for c in CATEGORICAL}
    X = feature_frame(df, categories)
    y = df.fraud_flag.astype(int).to_numpy()
    print(f"{len(df)} claims, {X.shape[1]} features")

    oof, importance = cross_validate(X, y, df.agent_id)
    metrics = report(df, y, oof, importance)
    write_scores(client, df, oof)

    final = new_model().fit(X, y)
    ARTIFACT_DIR.mkdir(exist_ok=True)
    path = ARTIFACT_DIR / "claims_model.joblib"
    joblib.dump({
        "model": final,
        "version": MODEL_VERSION,
        "features": list(X.columns),
        "categories": categories,
        "cv_metrics": metrics,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }, path)
    print(f"Saved {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}")


if __name__ == "__main__":
    main()
