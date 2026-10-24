"""Win-probability model: gradient boosting on Elo/form/H2H/workload features,
optionally blended with the de-vigged market price.

Uses scikit-learn's HistGradientBoostingClassifier (no extra native
dependency like xgboost/catboost, but the same family of algorithm and
comparable accuracy for a feature set this size). Validation is walk-forward
by season -- train on all seasons before year Y, evaluate on year Y -- which
is the only honest way to backtest a time series like match results.

## Why the market price is a feature

Measured on 66k matches (see `scripts/audit_edge.py`), out-of-sample log loss:

    Pinnacle's de-vigged price alone   0.594
    our features alone                 0.618
    our features + Pinnacle's price    0.595

Two things follow. First, blending the market in is a large, real improvement
to our *forecasts* (0.618 -> 0.595), so `use_market=True` is the default
whenever odds are available. Second -- and this is the uncomfortable one --
our features add nothing on top of the market (0.594 -> 0.595 is a slight
*worsening*). A model that cannot improve on the market price cannot
systematically beat it, no matter how it is tuned. The value of this model
is as a forecaster and a research tool, not as a money printer; see the
README's "Can this actually beat the bookmakers?" section.
"""
from __future__ import annotations

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss

from tennissharp.features import (FEATURE_COLUMNS, FEATURE_COLUMNS_WITH_MARKET,
                                   MARKET_FEATURE, attach_market_probability)


def feature_columns(use_market: bool) -> list[str]:
    return FEATURE_COLUMNS_WITH_MARKET if use_market else FEATURE_COLUMNS


def _can_use_market(table: pd.DataFrame) -> bool:
    return MARKET_FEATURE in table.columns and table[MARKET_FEATURE].notna().any()


def train(table: pd.DataFrame, use_market: bool | None = None) -> CalibratedClassifierCV:
    """Fit on the full feature table. Probabilities are isotonic-calibrated,
    since raw GBM outputs are usually overconfident -- and value betting
    lives or dies on the probabilities being well calibrated, not just the
    win/loss classification being accurate.

    `use_market=None` (the default) blends in the de-vigged market price when
    the table has one, and falls back to our features alone when it doesn't.
    The fitted model remembers which set it used, so `predict_proba` stays
    consistent without the caller having to track it.
    """
    if use_market is None:
        use_market = _can_use_market(table)
    if use_market and not _can_use_market(table):
        raise ValueError(
            f"use_market=True but '{MARKET_FEATURE}' is missing/empty. "
            "Call features.attach_market_probability(table) first."
        )

    cols = feature_columns(use_market)
    fit_on = table.dropna(subset=cols) if use_market else table
    X = fit_on[cols].astype(float)
    y = fit_on["label"].astype(int)

    base = HistGradientBoostingClassifier(
        max_depth=4, learning_rate=0.05, max_iter=300, l2_regularization=1.0,
        random_state=42,
    )
    model = CalibratedClassifierCV(base, method="isotonic", cv=5)
    model.fit(X, y)
    # Stash on the fitted estimator so predict_proba picks the same columns.
    model.tennissharp_uses_market_ = use_market
    return model


def predict_proba(model: CalibratedClassifierCV, table: pd.DataFrame) -> np.ndarray:
    """Returns P(player1 wins). Rows missing the market feature (when the
    model was trained with it) come back as NaN rather than silently scored
    against a fabricated price.
    """
    use_market = getattr(model, "tennissharp_uses_market_", False)
    cols = feature_columns(use_market)
    out = np.full(len(table), np.nan)
    usable = table[cols].notna().all(axis=1) if use_market else pd.Series(True, index=table.index)
    if usable.any():
        out[usable.to_numpy()] = model.predict_proba(table.loc[usable, cols].astype(float))[:, 1]
    return out


def walk_forward_evaluate(table: pd.DataFrame, min_train_seasons: int = 3,
                           use_market: bool | None = None) -> pd.DataFrame:
    """Train on all seasons < Y, predict season Y, roll forward season by
    season. One metrics row per held-out season.

    When the table carries a market price, the market's own log loss is
    reported alongside ours -- that is the number that actually matters, since
    a model that can't beat it can't beat the book.
    """
    if use_market is None:
        use_market = _can_use_market(table)

    seasons = sorted(table["date"].dt.year.unique())
    results = []
    for i, season in enumerate(seasons):
        if i < min_train_seasons:
            continue
        train_df = table[table["date"].dt.year < season]
        test_df = table[table["date"].dt.year == season]
        if train_df.empty or test_df.empty:
            continue
        model = train(train_df, use_market=use_market)
        preds = predict_proba(model, test_df)

        scored = ~np.isnan(preds)
        if scored.sum() == 0:
            continue
        preds, y_true = preds[scored], test_df["label"].to_numpy()[scored]

        row = {
            "season": season,
            "n_matches": int(scored.sum()),
            "accuracy": accuracy_score(y_true, preds > 0.5),
            "log_loss": log_loss(y_true, preds, labels=[0, 1]),
            "brier_score": brier_score_loss(y_true, preds),
        }
        if "market_prob_p1" in test_df.columns:
            market = test_df["market_prob_p1"].to_numpy()[scored]
            if not np.isnan(market).all():
                ok = ~np.isnan(market)
                row["market_log_loss"] = log_loss(y_true[ok], market[ok], labels=[0, 1])
                row["beats_market"] = bool(row["log_loss"] < row["market_log_loss"])
        results.append(row)
    return pd.DataFrame(results)


def save(model: CalibratedClassifierCV, path) -> None:
    joblib.dump(model, path)


def load(path) -> CalibratedClassifierCV:
    return joblib.load(path)
