"""Endpoints de backtest."""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from strategies.base import CryptoStrategy, PolymarketStrategy, Strategy, StrategyRegistry
from webapp.backend.engine import run_crypto_backtest, run_polymarket_backtest
from webapp.backend.markets.crypto import CryptoDataAdapter
from webapp.backend.markets.polymarket import PolymarketDataAdapter

logger = logging.getLogger("webapp.backtest")

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    strategy_id: str = Field(..., description="Strategy ID, ej 'polymarket.v1_alerts.V1Alerts'")
    period_start: Optional[str] = Field(None, description="ISO 8601, ej '2025-06-02'")
    period_end: Optional[str] = Field(None, description="ISO 8601")
    include_trades: bool = Field(True, description="Incluir lista de trades en respuesta")
    include_equity: bool = Field(True, description="Incluir equity curve")
    trades_limit: int = Field(500, description="Limite trades a devolver. 0 = todos")
    equity_points: int = Field(250, description="Downsample equity. 0 = todos")
    # Config overrides — permiten editar parametros sin tocar el codigo de la strategy
    overrides: Optional[dict] = Field(None, description="Sobrescribe atributos de la Strategy")


def _downsample_equity(points: list, target: int) -> list:
    if target <= 0 or len(points) <= target:
        return points
    step = len(points) / target
    out = [points[int(i * step)] for i in range(target)]
    if out[-1] != points[-1]:
        out.append(points[-1])
    return out


def _make_strategy_variant(base_cls: type[Strategy], overrides: dict) -> type[Strategy]:
    """Crea una subclass dinamica con overrides aplicados (one-shot, no se registra).

    Funciona tanto para Polymarket como para Crypto: itera sobre los overrides
    y solo aplica los que existen como atributo en la base class. Coerce tipos
    comunes (tupla, int, float, bool).
    """
    coerced: dict = {}
    for k, v in overrides.items():
        if not hasattr(base_cls, k):
            continue
        cur = getattr(base_cls, k)
        try:
            if isinstance(cur, tuple):
                coerced[k] = tuple(v) if isinstance(v, (list, tuple)) else (v,)
            elif isinstance(cur, bool):
                coerced[k] = bool(v)
            elif isinstance(cur, int) and not isinstance(cur, bool):
                coerced[k] = int(v)
            elif isinstance(cur, float):
                coerced[k] = float(v)
            else:
                coerced[k] = v
        except (TypeError, ValueError):
            continue
    if not coerced:
        return base_cls
    return type(f"{base_cls.__name__}_variant", (base_cls,), coerced)


# ---------------------------------------------------------------------------
#  Runners por mercado
# ---------------------------------------------------------------------------
def _run_polymarket(req: BacktestRequest, strategy: type[PolymarketStrategy]) -> dict:
    if req.overrides:
        strategy = _make_strategy_variant(strategy, req.overrides)  # type: ignore[assignment]

    universe = PolymarketDataAdapter.load_universe(strategy.dataset)
    if universe.empty:
        raise HTTPException(500, f"Dataset {strategy.dataset!r} esta vacio")

    ps = pd.to_datetime(req.period_start, utc=True) if req.period_start else None
    pe = pd.to_datetime(req.period_end, utc=True) if req.period_end \
        else pd.Timestamp.now(tz=timezone.utc)
    return run_polymarket_backtest(strategy, universe, ps, pe).to_dict()


def _run_crypto(req: BacktestRequest, strategy: type[CryptoStrategy]) -> dict:
    if req.overrides:
        strategy = _make_strategy_variant(strategy, req.overrides)  # type: ignore[assignment]

    # Para crypto, period_start/period_end definen el rango DE FETCH a Binance.
    start = req.period_start or "2024-01-01"
    end = req.period_end or pd.Timestamp.now(tz=timezone.utc).isoformat()

    try:
        klines = CryptoDataAdapter.load_klines(
            symbol=strategy.symbol,
            timeframe=strategy.timeframe,
            start=start,
            end=end,
            market="perp",
        )
    except Exception as exc:
        raise HTTPException(502, f"No pude cargar klines de Binance: {exc}") from exc

    if klines is None or klines.empty:
        raise HTTPException(404, f"No hay klines para {strategy.symbol} {strategy.timeframe} en {start}..{end}")

    return run_crypto_backtest(strategy, klines).to_dict()


# ---------------------------------------------------------------------------
#  Endpoints
# ---------------------------------------------------------------------------
@router.post("/run")
def run_backtest(req: BacktestRequest) -> dict:
    """Ejecuta un backtest sincronicamente y devuelve el resultado completo."""
    strategy = StrategyRegistry.get(req.strategy_id)
    if not strategy:
        raise HTTPException(404, f"Strategy not found: {req.strategy_id}")

    if strategy.market_type == "polymarket":
        payload = _run_polymarket(req, strategy)  # type: ignore[arg-type]
    elif strategy.market_type == "crypto_perp":
        payload = _run_crypto(req, strategy)  # type: ignore[arg-type]
    else:
        raise HTTPException(400, f"market_type no soportado: {strategy.market_type}")

    if not req.include_trades:
        payload["trades"] = []
    elif req.trades_limit > 0 and len(payload["trades"]) > req.trades_limit:
        payload["trades"] = payload["trades"][-req.trades_limit:]

    if not req.include_equity:
        payload["equity_curve"] = []
    else:
        payload["equity_curve"] = _downsample_equity(payload["equity_curve"], req.equity_points)
    return payload


@router.get("/data-info")
def data_info() -> dict:
    """Metadata sobre los datasets disponibles."""
    return PolymarketDataAdapter.info()


@router.post("/export")
def export_trades(req: BacktestRequest) -> StreamingResponse:
    """Exporta los trades del backtest a CSV (solo polymarket por ahora)."""
    strategy = StrategyRegistry.get(req.strategy_id)
    if not strategy:
        raise HTTPException(404, f"Strategy not found: {req.strategy_id}")
    if strategy.market_type != "polymarket":
        raise HTTPException(400, "Export CSV solo soportado para polymarket por ahora")
    poly_strat: type[PolymarketStrategy] = strategy  # type: ignore[assignment]
    if req.overrides:
        poly_strat = _make_strategy_variant(poly_strat, req.overrides)  # type: ignore[assignment]
    universe = PolymarketDataAdapter.load_universe(poly_strat.dataset)
    ps = pd.to_datetime(req.period_start, utc=True) if req.period_start else None
    pe = pd.to_datetime(req.period_end, utc=True) if req.period_end else pd.Timestamp.now(tz=timezone.utc)
    result = run_polymarket_backtest(poly_strat, universe, ps, pe)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "timestamp", "asset", "direction", "entry_price", "exit_price",
        "stake_usd", "cost_paid", "pnl", "is_winner", "bankroll_after",
        "edge_signed", "p_poly", "p_fair", "volume_usd",
    ])
    for t in result.trades:
        writer.writerow([
            t.timestamp, t.asset, t.direction, t.entry_price, t.exit_price,
            t.stake_usd, t.cost_paid, t.pnl, t.is_winner, t.bankroll_after,
            t.extra.get("edge_signed", ""), t.extra.get("p_poly", ""),
            t.extra.get("p_fair", ""), t.extra.get("volume_usd", ""),
        ])
    buf.seek(0)
    fname = f"{strategy.__name__}_trades_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@router.post("/breakdowns")
def breakdowns(req: BacktestRequest) -> dict:
    """Devuelve breakdowns del backtest: por asset, hora UTC, dia semana, edge buckets.

    Solo polymarket por ahora — para crypto los breakdowns relevantes son distintos
    (por hora del dia, por bucket de volatilidad, etc.) y se implementaran aparte.
    """
    strategy = StrategyRegistry.get(req.strategy_id)
    if not strategy:
        raise HTTPException(404, f"Strategy not found: {req.strategy_id}")
    if strategy.market_type != "polymarket":
        raise HTTPException(400, "Breakdowns solo soportado para polymarket por ahora")
    poly_strat: type[PolymarketStrategy] = strategy  # type: ignore[assignment]
    if req.overrides:
        poly_strat = _make_strategy_variant(poly_strat, req.overrides)  # type: ignore[assignment]
    universe = PolymarketDataAdapter.load_universe(poly_strat.dataset)
    ps = pd.to_datetime(req.period_start, utc=True) if req.period_start else None
    pe = pd.to_datetime(req.period_end, utc=True) if req.period_end else pd.Timestamp.now(tz=timezone.utc)
    result = run_polymarket_backtest(poly_strat, universe, ps, pe)

    if not result.trades:
        return {
            "by_asset": [], "by_hour": [], "by_weekday": [],
            "pnl_histogram": [], "drawdown_curve": [], "duration_seconds": result.duration_seconds,
        }

    df = pd.DataFrame([{
        "ts": pd.to_datetime(t.timestamp, utc=True),
        "asset": t.asset,
        "direction": t.direction,
        "pnl": t.pnl,
        "is_winner": t.is_winner,
        "edge_abs": abs(t.extra.get("edge_signed", 0)),
        "bankroll_after": t.bankroll_after,
    } for t in result.trades])
    df["hour"] = df["ts"].dt.hour
    df["weekday"] = df["ts"].dt.day_name()

    # Por asset
    by_asset = []
    for asset, g in df.groupby("asset"):
        wins = int(g["is_winner"].sum())
        by_asset.append({
            "asset": asset,
            "trades": int(len(g)),
            "wins": wins,
            "losses": int(len(g) - wins),
            "win_rate_pct": round(100 * wins / len(g), 1) if len(g) else 0.0,
            "pnl_total": round(float(g["pnl"].sum()), 2),
            "pnl_avg": round(float(g["pnl"].mean()), 3),
        })
    by_asset.sort(key=lambda x: x["pnl_total"], reverse=True)

    # Por hora UTC
    by_hour = []
    for h in range(24):
        g = df[df["hour"] == h]
        if len(g) == 0:
            by_hour.append({"hour": h, "trades": 0, "win_rate_pct": 0.0, "pnl_total": 0.0, "pnl_avg": 0.0})
            continue
        wins = int(g["is_winner"].sum())
        by_hour.append({
            "hour": h,
            "trades": int(len(g)),
            "win_rate_pct": round(100 * wins / len(g), 1),
            "pnl_total": round(float(g["pnl"].sum()), 2),
            "pnl_avg": round(float(g["pnl"].mean()), 3),
        })

    # Por dia
    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    by_weekday = []
    for d in weekday_order:
        g = df[df["weekday"] == d]
        if len(g) == 0:
            by_weekday.append({"weekday": d, "trades": 0, "win_rate_pct": 0.0, "pnl_total": 0.0, "pnl_avg": 0.0})
            continue
        wins = int(g["is_winner"].sum())
        by_weekday.append({
            "weekday": d,
            "trades": int(len(g)),
            "win_rate_pct": round(100 * wins / len(g), 1),
            "pnl_total": round(float(g["pnl"].sum()), 2),
            "pnl_avg": round(float(g["pnl"].mean()), 3),
        })

    # Histograma PnL — 30 buckets
    pnls = df["pnl"].values
    pnl_min = float(pnls.min())
    pnl_max = float(pnls.max())
    n_buckets = 30
    if pnl_max > pnl_min:
        step = (pnl_max - pnl_min) / n_buckets
        hist = []
        for i in range(n_buckets):
            lo = pnl_min + i * step
            hi = lo + step
            count = int(((pnls >= lo) & (pnls < hi)).sum())
            hist.append({"bucket_lo": round(lo, 2), "bucket_hi": round(hi, 2), "count": count})
        # Edge case: incluir el max en el ultimo bucket
        hist[-1]["count"] += int((pnls == pnl_max).sum() - ((pnls >= pnl_min + (n_buckets-1)*step) & (pnls < pnl_max)).sum())
    else:
        hist = [{"bucket_lo": pnl_min, "bucket_hi": pnl_max, "count": len(pnls)}]

    # Drawdown curve (% desde el peak)
    initial = result.initial_bankroll
    peak = initial
    dd_curve = []
    for t in result.trades:
        peak = max(peak, t.bankroll_after)
        dd_pct = (t.bankroll_after - peak) / peak * 100 if peak > 0 else 0.0
        dd_curve.append({"timestamp": t.timestamp, "drawdown_pct": round(dd_pct, 2)})
    # Downsample dd_curve a max 250
    if len(dd_curve) > 250:
        step = len(dd_curve) / 250
        dd_curve = [dd_curve[int(i * step)] for i in range(250)]

    return {
        "by_asset": by_asset,
        "by_hour": by_hour,
        "by_weekday": by_weekday,
        "pnl_histogram": hist,
        "drawdown_curve": dd_curve,
        "duration_seconds": result.duration_seconds,
        "summary": {
            "n_trades": len(result.trades),
            "win_rate_pct": result.metrics["win_rate_pct"],
            "total_pnl": result.total_pnl,
        },
    }
