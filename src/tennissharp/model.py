"""Win-probability model: gradient boosting on Elo/form/H2H features.

Uses scikit-learn's HistGradientBoostingClassifier (no extra native
dependency like xgboost/catboost, but the same family of algorithm and
comparable accuracy for a feature set this size). Validation is walk-forward
by season -- train on all seasons before year Y, evaluate on year Y -- which
is the only honest way to backtest a time series like match results.
"""
from __future__ import annotations

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss

from tennissharp.features import FEATURE_COLUMNS


def _xy(table: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    X = table[FEATURE_COLUMNS].astype(float)
    y = table["label"].astype(int)
    return X, y


def train(table: pd.DataFrame) -> CalibratedClassifierCV:
    """Fit on the full feature table. Probabilities are isotonic-calibrated,
    since raw GBM outputs are usually overconfident -- and value betting
    lives or dies on the probabilities being well calibrated, not just the
    win/loss classification being accurate.
    """
    X, y = _xy(table)
    base = HistGradientBoostingClassifier(
        max_depth=4, learning_rate=0.05, max_iter=300, l2_regularization=1.0,
        random_state=42,
    )
    model = CalibratedClassifierCV(base, method="isotonic", cv=5)
    model.fit(X, y)
    return model


def predict_proba(model: CalibratedClassifierCV, table: pd.DataFrame) -> np.ndarray:
    X = table[FEATURE_COLUMNS].astype(float)
    return model.predict_proba(X)[:, 1]


def walk_forward_evaluate(table: pd.DataFrame, min_train_seasons: int = 3) -> pd.DataFrame:
    """Train on all seasons < Y, predict season Y, roll forward season by
    season. Returns one metrics row per held-out season plus predictions
    attached to `table` are NOT mutated -- callers get predictions back via
    the returned dataframe's `oos_predictions` if needed.
    """
    seasons = sorted(table["date"].dt.year.unique())
    results = []
    for i, season in enumerate(seasons):
        if i < min_train_seasons:
            continue
        train_df = table[table["date"].dt.year < season]
        test_df = table[table["date"].dt.year == season]
        if train_df.empty or test_df.empty:
            continue
        model = train(train_df)
        preds = predict_proba(model, test_df)
        y_true = test_df["label"].to_numpy()
        results.append({
            "season": season,
            "n_matches": len(test_df),
            "accuracy": accuracy_score(y_true, preds > 0.5),
            "log_loss": log_loss(y_true, preds, labels=[0, 1]),
            "brier_score": brier_score_loss(y_true, preds),
        })
    return pd.DataFrame(results)


def save(model: CalibratedClassifierCV, path) -> None:
    joblib.dump(model, path)


def load(path) -> CalibratedClassifierCV:
    return joblib.load(path)
