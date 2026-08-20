"""REST API for building your own app (mobile, web, whatever) on top of the
TennisSharpBot data/model pipeline. Thin JSON wrapper around service.py --
see that module for what each endpoint actually reads and why.

Run with: uvicorn tennissharp.api:app --host 0.0.0.0 --port 8000
(or `python scripts/run_api.py`).
"""
from __future__ import annotations

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from tennissharp import service

app = FastAPI(
    title="TennisSharpBot API",
    description="Surface-Elo ratings, surface speed, schedules/odds, H2H, and value bets. "
                "Not financial advice -- see the project README's disclaimer.",
    version="1.0.0",
)


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> JSON-safe list of dicts (handles NaT/NaN/Timestamp)."""
    return df.replace({pd.NaT: None}).where(pd.notna(df), None).astype(object).to_dict(orient="records")


@app.exception_handler(service.DataNotReadyError)
async def _not_ready_handler(request, exc: service.DataNotReadyError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/rankings")
def rankings(tour: str = Query("atp", pattern="^(atp|wta)$"),
             source: str = Query("ta", pattern="^(ta|own)$"),
             top_n: int = Query(10, ge=1, le=200)) -> list[dict]:
    df = service.get_rankings(tour=tour, top_n=top_n, source=source)
    return _records(df)


@app.get("/rankings/wta-general")
def wta_general_rankings(top_n: int = Query(10, ge=1, le=200)) -> list[dict]:
    """The standalone WTA Elo file -- overall rating plus the hElo/cElo/gElo
    surface splits."""
    df = service.get_wta_general_rankings(top_n=top_n)
    return _records(df)


@app.get("/rankings/atp-general")
def atp_general_rankings(top_n: int = Query(10, ge=1, le=200)) -> list[dict]:
    """The standalone ATP Elo file -- overall rating plus the hElo/cElo/gElo
    surface splits."""
    df = service.get_atp_general_rankings(top_n=top_n)
    return _records(df)


@app.get("/leaders")
def leaders(tour: str = Query("atp", pattern="^(atp|wta)$"),
            pool: str = Query("top50", pattern="^(top50|51-100|challenger)$"),
            stat: str = Query("serve", pattern="^(serve|return)$"),
            surface: str = Query("all", pattern="^(all|hard|clay|grass|carpet)$"),
            top_n: int = Query(50, ge=1, le=200)) -> list[dict]:
    """Serve/Return stat leaderboard, overall or filtered to one surface --
    see service.get_leaders. WTA has no Challenger pool."""
    df = service.get_leaders(tour=tour, pool=pool, stat=stat, surface=surface, top_n=top_n)
    return _records(df)


@app.get("/surface-speed")
def surface_speed(tournament: str | None = None, top_n: int = Query(10, ge=1, le=100)) -> list[dict]:
    df = service.get_surface_speed(tournament=tournament, top_n=top_n)
    return _records(df)


@app.get("/upcoming")
def upcoming(tour: str | None = Query(None, pattern="^(atp|wta)$"),
             limit: int = Query(20, ge=1, le=200)) -> list[dict]:
    df = service.get_upcoming_matches(tour=tour, limit=limit)
    return _records(df)


@app.get("/h2h")
def head_to_head(player1: str, player2: str) -> dict:
    try:
        result = service.get_head_to_head(player1, player2)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "player1": result["player1"], "player2": result["player2"],
        "wins1": result["wins1"], "wins2": result["wins2"],
        "history": _records(result["history"]),
    }


@app.get("/odds-history")
def odds_history(player1: str, player2: str) -> dict:
    """Odds-movement timeline ("Quotenverlauf") for a scheduled match,
    looked up by player names -- see service.get_odds_history."""
    try:
        result = service.get_odds_history(player1, player2)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "player1": result["player1"], "player2": result["player2"], "match_id": result["match_id"],
        "history": _records(result["history"]),
    }


@app.get("/value-bets")
def value_bets(edge_threshold: float = Query(0.03, ge=0, le=1),
               kelly_fraction: float = Query(0.25, ge=0, le=1),
               bankroll: float = Query(10_000.0, gt=0)) -> list[dict]:
    try:
        df = service.get_value_bets(edge_threshold=edge_threshold, kelly_fraction=kelly_fraction,
                                     bankroll=bankroll)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _records(df)
