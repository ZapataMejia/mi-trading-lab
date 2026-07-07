"""Endpoints avanzados: walk-forward validation y grid search.

- /api/advanced/walk-forward → divide el periodo en ventanas, corre backtest en cada una
- /api/advanced/grid-search  → corre backtest sobre un producto cartesiano de overrides
"""
from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from strategies.base import PolymarketStrategy, StrategyRegistry
from webapp.backend.engine import run_polymarket_backtest
from webapp.backend.markets.polymarket import PolymarketDataAdapter

from .backtest_api import _make_strategy_variant

logger = logging.getLogger("webapp.advanced")
router = APIRouter(prefix="/api/advanced", tags=["advanced"])


class WalkForwardRequest(BaseModel):
    strategy_id: str
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    n_windows: int = Field(6, ge=2, le=24, description="Numero de ventanas a generar")
    overrides: Optional[dict] = None


@router.post("/walk-forward")
def walk_forward(req: WalkForwardRequest) -> dict:
    """Divide el periodo en N ventanas contiguas, corre backtest en cada una."""
    strategy = StrategyRegistry.get(req.strategy_id)
    if not strategy:
        raise HTTPException(404, f"Strategy not found: {req.strategy_id}")
    if strategy.market_type != "polymarket":
        raise HTTPException(400, "Walk-forward solo soportado en polymarket por ahora")

    poly_strat: type[PolymarketStrategy] = strategy  # type: ignore[assignment]
    if req.overrides:
        poly_strat = _make_strategy_variant(poly_strat, req.overrides)

    universe = PolymarketDataAdapter.load_universe(poly_strat.dataset)
    ps = pd.to_datetime(req.period_start, utc=True) if req.period_start else None
    pe = pd.to_datetime(req.period_end, utc=True) if req.period_end else pd.Timestamp.now(tz="UTC")

    # Inferir rango si no viene — usar la primera columna timestamp-like que encontremos
    if ps is None:
        ts_col = next(
            (c for c in ("timestamp_utc", "window_start", "window_end_utc", "snapshot_utc", "snapshot_at", "ts") if c in universe.columns),
            None,
        )
        if not ts_col:
            raise HTTPException(500, f"No timestamp column en dataset; cols={list(universe.columns)[:8]}")
        ps = pd.to_datetime(universe[ts_col].min(), utc=True)

    total_seconds = (pe - ps).total_seconds()
    if total_seconds <= 0:
        raise HTTPException(400, "Periodo invalido")
    window_seconds = total_seconds / req.n_windows

    windows = []
    for i in range(req.n_windows):
        w_start = ps + pd.Timedelta(seconds=i * window_seconds)
        w_end = ps + pd.Timedelta(seconds=(i + 1) * window_seconds)
        result = run_polymarket_backtest(poly_strat, universe, w_start, w_end)
        windows.append({
            "index": i,
            "period_start": w_start.isoformat(),
            "period_end": w_end.isoformat(),
            "n_trades": result.metrics["n_trades"],
            "win_rate_pct": result.metrics["win_rate_pct"],
            "total_pnl": result.total_pnl,
            "total_pnl_pct": result.total_pnl_pct,
            "sharpe": result.metrics["sharpe"],
            "sortino": result.metrics["sortino"],
            "max_drawdown_pct": result.metrics["max_drawdown_pct"],
            "profit_factor": result.metrics["profit_factor"],
        })

    pnls = [w["total_pnl"] for w in windows]
    profitable = sum(1 for p in pnls if p > 0)
    summary = {
        "n_windows": req.n_windows,
        "n_profitable": profitable,
        "consistency_pct": round(100 * profitable / req.n_windows, 1),
        "avg_pnl_per_window": round(sum(pnls) / req.n_windows, 2) if pnls else 0,
        "best_window_pnl": round(max(pnls), 2) if pnls else 0,
        "worst_window_pnl": round(min(pnls), 2) if pnls else 0,
        "total_pnl_aggregated": round(sum(pnls), 2),
    }
    return {"windows": windows, "summary": summary}


class GridSearchRequest(BaseModel):
    strategy_id: str
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    # grid: dict de param_name -> lista de valores a probar
    # ej: {"threshold": [0.05, 0.10, 0.15, 0.20], "min_volume_usd": [0, 5000]}
    grid: dict[str, list[Any]] = Field(..., description="Diccionario param -> lista de valores")
    max_combinations: int = Field(50, ge=1, le=200, description="Cap de combinaciones para no explotar")


@router.post("/grid-search")
def grid_search(req: GridSearchRequest) -> dict:
    strategy = StrategyRegistry.get(req.strategy_id)
    if not strategy:
        raise HTTPException(404, f"Strategy not found: {req.strategy_id}")
    if strategy.market_type != "polymarket":
        raise HTTPException(400, "Grid search solo soportado en polymarket por ahora")

    base: type[PolymarketStrategy] = strategy  # type: ignore[assignment]
    universe = PolymarketDataAdapter.load_universe(base.dataset)
    ps = pd.to_datetime(req.period_start, utc=True) if req.period_start else None
    pe = pd.to_datetime(req.period_end, utc=True) if req.period_end else pd.Timestamp.now(tz="UTC")

    keys = list(req.grid.keys())
    values = [req.grid[k] for k in keys]
    combos = list(itertools.product(*values))
    if len(combos) > req.max_combinations:
        raise HTTPException(400, f"{len(combos)} combinaciones > max {req.max_combinations}. Reduci el grid.")

    results = []
    for combo in combos:
        overrides = dict(zip(keys, combo))
        variant = _make_strategy_variant(base, overrides)
        r = run_polymarket_backtest(variant, universe, ps, pe)
        results.append({
            "params": overrides,
            "n_trades": r.metrics["n_trades"],
            "win_rate_pct": r.metrics["win_rate_pct"],
            "total_pnl": r.total_pnl,
            "total_pnl_pct": r.total_pnl_pct,
            "sharpe": r.metrics["sharpe"],
            "max_drawdown_pct": r.metrics["max_drawdown_pct"],
            "profit_factor": r.metrics["profit_factor"],
        })

    # Ordenar por sharpe descending
    results.sort(key=lambda x: (x["sharpe"] if x["sharpe"] is not None else -999), reverse=True)

    return {
        "param_names": keys,
        "n_combinations": len(combos),
        "results": results,
        "best": results[0] if results else None,
    }
