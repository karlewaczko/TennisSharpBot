#!/usr/bin/env python3
"""Leak-free serve/return ratings from the TennisMyLife history.

Every point-based tennis model (Klaassen & Magnus and everything after
it) is built on one quantity: the share of points a player wins behind
his own serve, and the share he wins returning. Our feature set never
had it, because tennis-data.co.uk carries no match statistics at all.

Ratings are exponentially weighted and read strictly *before* each match
is used to update them, so a row never sees its own result. They are
computed over the full 195k-match TennisMyLife history -- main tour,
challenger, qualifying and WTA -- which is 2.4x what our own feed covers
and includes the players our Elo loses track of.
"""
import _bootstrap  # noqa: F401
import argparse
from collections import defaultdict

import pandas as pd

from tennissharp import config
from tennissharp.data import tennismylife as tml

# Half-life in matches. Serve form moves faster than overall standard, and
# a shorter memory than Elo's is the point of having this separately.
DECAY = 0.97
PRIOR_SERVE = 0.62          # tour-wide serve-point win rate
PRIOR_RETURN = 1 - PRIOR_SERVE
MIN_WEIGHT = 3.0            # below this the rating is mostly prior


class ServeRatings:
    """Running serve/return point-win rates, overall and per surface."""

    def __init__(self, decay=DECAY):
        self.decay = decay
        self._num = defaultdict(float)   # weighted points won
        self._den = defaultdict(float)   # weighted points played

    def _key(self, player, kind, surface=None):
        return (player, kind, surface)

    def get(self, player, surface):
        out = {}
        for kind, prior in (("serve", PRIOR_SERVE), ("return", PRIOR_RETURN)):
            for surf, label in ((None, ""), (surface, "_surface")):
                k = self._key(player, kind, surf)
                den = self._den[k]
                # Shrink toward the tour prior while the sample is thin --
                # a player with two matches must not read as elite.
                w = den / (den + MIN_WEIGHT) if den else 0.0
                rate = (self._num[k] / den) if den else prior
                out[f"{kind}{label}"] = w * rate + (1 - w) * prior
        return out

    def update(self, player, surface, won, played, kind):
        if not played or played <= 0:
            return
        for surf in (None, surface):
            k = self._key(player, kind, surf)
            self._num[k] = self._num[k] * self.decay + won
            self._den[k] = self._den[k] * self.decay + played


def build(matches: pd.DataFrame) -> pd.DataFrame:
    """One row per match with both players' pre-match serve/return ratings."""
    ratings = ServeRatings()
    rows = []
    cols = ["date", "winner", "loser", "surface", "match_id",
            "winner_svpt", "winner_1stwon", "winner_2ndwon",
            "loser_svpt", "loser_1stwon", "loser_2ndwon"]
    for r in matches[cols].itertuples(index=False):
        w_pre = ratings.get(r.winner, r.surface)
        l_pre = ratings.get(r.loser, r.surface)
        rows.append({
            "match_id": r.match_id, "date": r.date,
            "winner": r.winner, "loser": r.loser,
            "w_serve": w_pre["serve"], "l_serve": l_pre["serve"],
            "w_return": w_pre["return"], "l_return": l_pre["return"],
            "w_serve_surface": w_pre["serve_surface"],
            "l_serve_surface": l_pre["serve_surface"],
            "w_return_surface": w_pre["return_surface"],
            "l_return_surface": l_pre["return_surface"],
        })
        # Update only from matches that actually carry a serve line.
        w_pts, l_pts = r.winner_svpt, r.loser_svpt
        if pd.notna(w_pts) and pd.notna(l_pts) and w_pts > 0 and l_pts > 0:
            w_won = (r.winner_1stwon or 0) + (r.winner_2ndwon or 0)
            l_won = (r.loser_1stwon or 0) + (r.loser_2ndwon or 0)
            ratings.update(r.winner, r.surface, w_won, w_pts, "serve")
            ratings.update(r.loser, r.surface, l_won, l_pts, "serve")
            # Returning is the mirror: points won receiving the opponent's serve.
            ratings.update(r.winner, r.surface, l_pts - l_won, l_pts, "return")
            ratings.update(r.loser, r.surface, w_pts - w_won, w_pts, "return")
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=str(config.PROCESSED_DIR / "serve_ratings.csv"))
    args = ap.parse_args()
    matches = tml.load_all()
    print(f"{len(matches)} Partien aus TennisMyLife")
    table = build(matches)
    table.to_csv(args.out, index=False)
    print(f"{len(table)} Zeilen -> {args.out}")
    print(table[["w_serve", "l_serve", "w_return", "l_return"]].describe().to_string())


if __name__ == "__main__":
    main()
