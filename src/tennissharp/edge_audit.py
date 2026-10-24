"""Tools that tell you whether an edge is real -- or whether you are fooling
yourself.

Every one of these exists because the alternative is losing money slowly
while a backtest says otherwise. In this repo's own history, two of the four
checks below overturned a result that looked like a +8% ROI strategy:

1. `price_attainability_report` -- a "best available odds" column that shows
   arbitrage on 44% of matches is not a snapshot of simultaneously available
   prices, it is a running maximum over the market's lifetime. You cannot bet
   a price that existed for ten minutes three days ago. Backtesting against
   it manufactures free money out of nothing.
2. `market_calibration_report` -- before trying to beat a market, check
   whether it is actually beatable. Pinnacle's de-vigged tennis prices match
   realised win rates to within about a percentage point across the whole
   probability range, on 150k+ observations.
3. `incremental_information_test` -- the sharpest question available: given
   the market's price, do your features add anything? If a model trained on
   [market price + your features] does not beat one trained on [market price]
   alone, out of sample, then you hold no information the market lacks, and
   no amount of tuning will produce an edge.
4. `roi_with_significance` / `segment_report` -- an ROI without a standard
   error is a rumour. Tennis betting ROIs have enormous variance; +5% over
   500 bets is entirely consistent with a true edge of zero.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from tennissharp.odds_math import shin_devig

# A simultaneous best-line snapshot across real books shows cross-book
# arbitrage on a low single-digit percentage of tennis matches. Well above
# that means the column is a maximum over time, not a purchasable price.
PLAUSIBLE_ARB_RATE = 0.05


def devig_pair(odds_a: float, odds_b: float) -> tuple[float, float]:
    fair = shin_devig([odds_a, odds_b])
    return float(fair[0]), float(fair[1])


def price_attainability_report(matches: pd.DataFrame,
                                price_cols: dict[str, tuple[str, str]] | None = None
                                ) -> pd.DataFrame:
    """For each odds column pair, how often does it imply a negative overround?

    A real bookmaker never books a negative overround, and simultaneous
    cross-book arbitrage is rare. A high rate flags a column as
    NOT ATTAINABLE -- do not backtest against it.
    """
    price_cols = price_cols or {
        "pinnacle": ("pinnacle_w", "pinnacle_l"),
        "bet365": ("bet365_w", "bet365_l"),
        "market_avg": ("market_avg_w", "market_avg_l"),
        "market_max": ("market_max_w", "market_max_l"),
    }
    rows = []
    for label, (wc, lc) in price_cols.items():
        if wc not in matches.columns or lc not in matches.columns:
            continue
        sub = matches[[wc, lc]].dropna()
        if sub.empty:
            continue
        overround = 1 / sub[wc] + 1 / sub[lc] - 1
        arb_rate = float((overround < 0).mean())
        rows.append({
            "price_column": label,
            "n": len(sub),
            "mean_overround": round(float(overround.mean()), 5),
            "negative_overround_rate": round(arb_rate, 4),
            "attainable": arb_rate <= PLAUSIBLE_ARB_RATE,
            "verdict": ("looks like a real quotable price" if arb_rate <= PLAUSIBLE_ARB_RATE
                        else "NOT ATTAINABLE -- running max over time, do not bet/backtest this"),
        })
    return pd.DataFrame(rows)


def market_calibration_report(matches: pd.DataFrame, odds_prefix: str = "pinnacle",
                               n_buckets: int = 10) -> pd.DataFrame:
    """Bucket the market's de-vigged probabilities and compare each bucket to
    the realised win rate. Close agreement = the market is efficient and you
    should not expect to out-predict it.
    """
    wc, lc = f"{odds_prefix}_w", f"{odds_prefix}_l"
    sub = matches[[wc, lc]].dropna()
    if sub.empty:
        return pd.DataFrame()

    fair = np.array([shin_devig([a, b]) for a, b in zip(sub[wc], sub[lc])])
    # Each match contributes both sides, so the comparison is symmetric:
    # the winner's side realised 1, the loser's side realised 0.
    long = pd.DataFrame({
        "market_prob": np.concatenate([fair[:, 0], fair[:, 1]]),
        "won": np.concatenate([np.ones(len(sub)), np.zeros(len(sub))]),
    })
    long["bucket"] = pd.cut(long.market_prob, bins=np.linspace(0, 1, n_buckets + 1))
    out = (long.groupby("bucket", observed=True)
                .agg(n=("won", "size"), market_implied=("market_prob", "mean"),
                     actual_win_rate=("won", "mean"))
                .reset_index())
    out["error"] = out.actual_win_rate - out.market_implied
    out["market_implied"] = out.market_implied.round(4)
    out["actual_win_rate"] = out.actual_win_rate.round(4)
    out["error"] = out.error.round(4)
    return out


def roi_with_significance(won: np.ndarray, price: np.ndarray) -> dict:
    """Flat-stake ROI plus the standard error and t-statistic that say whether
    it is distinguishable from zero. |t| < 2 means "no evidence of an edge",
    however pretty the ROI looks.
    """
    won = np.asarray(won, dtype=float)
    price = np.asarray(price, dtype=float)
    if len(won) == 0:
        return {"n_bets": 0, "roi": None, "std_error": None, "t_stat": None,
                "significant": False}
    pnl = np.where(won == 1, price - 1.0, -1.0)
    roi = float(pnl.mean())
    se = float(pnl.std(ddof=1) / np.sqrt(len(pnl))) if len(pnl) > 1 else float("nan")
    t = roi / se if se and not np.isnan(se) and se > 0 else 0.0
    return {
        "n_bets": int(len(pnl)),
        "roi": round(roi, 5),
        "std_error": round(se, 5) if se == se else None,
        "t_stat": round(float(t), 2),
        "significant": bool(abs(t) >= 2.0),
        "interpretation": ("consistent with zero edge -- do not bet this"
                           if abs(t) < 2.0 else
                           "statistically distinguishable from zero (still check for bias)"),
    }


def incremental_information_test(table: pd.DataFrame, feature_columns: list[str],
                                  market_prob_col: str = "market_prob_p1",
                                  label_col: str = "label",
                                  min_train_seasons: int = 3) -> pd.DataFrame:
    """Walk-forward: does [market + our features] beat [market] out of sample?

    Returns one row per held-out season with the log loss of the market alone,
    our features alone, and the two combined. The summary line that matters is
    `market_log_loss - combined_log_loss`: positive means we carry information
    the market lacks; zero or negative means we do not, and therefore cannot
    beat it.
    """
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import log_loss

    work = table.dropna(subset=[market_prob_col] + feature_columns).copy()
    work["season"] = work["date"].dt.year
    clipped = work[market_prob_col].clip(1e-6, 1 - 1e-6)
    work["_market_logit"] = np.log(clipped / (1 - clipped))

    seasons = sorted(work.season.unique())
    rows = []
    for i, season in enumerate(seasons):
        if i < min_train_seasons:
            continue
        tr, te = work[work.season < season], work[work.season == season]
        if len(tr) < 2000 or len(te) < 300:
            continue
        ytr, yte = tr[label_col].to_numpy(), te[label_col].to_numpy()

        def _ll(cols):
            m = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05,
                                                max_iter=300, l2_regularization=1.0,
                                                random_state=42)
            m.fit(tr[cols].astype(float), ytr)
            return float(log_loss(yte, m.predict_proba(te[cols].astype(float))[:, 1],
                                   labels=[0, 1]))

        rows.append({
            "season": int(season),
            "n": len(te),
            "market_log_loss": float(log_loss(yte, te[market_prob_col], labels=[0, 1])),
            "ours_log_loss": _ll(feature_columns),
            "combined_log_loss": _ll(["_market_logit"] + feature_columns),
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out["we_add_information"] = out.combined_log_loss < out.market_log_loss - 1e-4
    return out


def summarize_incremental(report: pd.DataFrame) -> dict:
    if report.empty:
        return {"verdict": "not enough data to run the test"}
    n = report.n.sum()
    wavg = lambda c: float((report[c] * report.n).sum() / n)
    market, ours, combined = wavg("market_log_loss"), wavg("ours_log_loss"), wavg("combined_log_loss")
    gain = market - combined
    if gain > 0.005:
        verdict = "our features add real information beyond the market -- an edge is plausible"
    elif gain > 0.001:
        verdict = "marginal information beyond the market -- likely too small to overcome the vig"
    else:
        verdict = ("NO information beyond the market: the market already prices in "
                   "everything we know, so this model cannot systematically beat it")
    return {
        "seasons_tested": int(len(report)),
        "matches_tested": int(n),
        "market_log_loss": round(market, 5),
        "ours_log_loss": round(ours, 5),
        "combined_log_loss": round(combined, 5),
        "information_gain": round(gain, 5),
        "market_lifts_our_model_by": round(ours - combined, 5),
        "verdict": verdict,
    }


def segment_report(bets: pd.DataFrame, by: str, price_col: str = "price",
                    won_col: str = "won", min_bets: int = 50) -> pd.DataFrame:
    """Break a set of bets down by a column and report ROI + significance for
    each segment, so an aggregate number can't hide where it came from.

    Treat this as exploratory only: slicing a dataset enough ways will always
    surface a "profitable" segment by chance. A segment is worth taking
    seriously only if it was hypothesised in advance and holds up out of sample.
    """
    rows = []
    for value, grp in bets.groupby(by, observed=True):
        if len(grp) < min_bets:
            continue
        stats = roi_with_significance(grp[won_col].to_numpy(), grp[price_col].to_numpy())
        stats[by] = value
        rows.append(stats)
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    cols = [by] + [c for c in out.columns if c != by]
    return out[cols].sort_values("roi", ascending=False).reset_index(drop=True)
