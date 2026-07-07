"""API Fondeo Lab — backtest EMA sin AlgoWizard."""
from __future__ import annotations

import gc
import itertools
import json
import logging
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from webapp.backend.engine.fondeo_engine import FondeoConfig, run_fondeo_backtest
from webapp.backend.engine.hedged_eval import run_hedged_backtest, simulate_hedged_windows
from webapp.backend.engine.liquidity_sweep_engine import LiquiditySweepConfig, run_liquidity_sweep
from webapp.backend.engine.ws_eval import evaluate_ws_classic, simulate_eval_windows
from webapp.backend.markets.forex import ForexDataAdapter

logger = logging.getLogger("webapp.fondeo")

router = APIRouter(prefix="/api/fondeo", tags=["fondeo"])

_VALIDATE_CACHE = Path("data/forex_cache/liq_sweep_validate_2022_2024.json")
_HEAVY_SIM_LOCK = threading.Lock()


def _online_mode() -> bool:
    return os.getenv("ONLINE_MODE", "0").strip().lower() in ("1", "true", "yes")


def _max_sim_days() -> int:
    for key in ("MAX_FONDEO_SIM_DAYS", "MAX_LIQ_SIM_DAYS"):
        raw = os.getenv(key, "").strip()
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
    return 90 if _online_mode() else 0


def max_sim_days_for_ui() -> int:
    """Límite que el frontend muestra y valida (0 backend = sin tope → reportar 730)."""
    limit = _max_sim_days()
    return limit if limit > 0 else 730


def _check_period_limit(start: str | None, end: str | None) -> None:
    if _online_mode() and (not start or not end):
        raise HTTPException(
            400,
            "En la nube debes indicar period_start y period_end (máx. 90 días por simulación).",
        )
    max_days = _max_sim_days()
    if max_days <= 0:
        return
    days = _period_days(start, end)
    if days is not None and days > max_days:
        raise HTTPException(
            400,
            f"Periodo demasiado largo ({days} días). Máximo {max_days} días por simulación.",
        )


def _reject_if_online_only_local(action: str) -> None:
    if _online_mode():
        raise HTTPException(503, f"{action} solo disponible en la versión local.")


@contextmanager
def _heavy_sim_slot():
    if not _HEAVY_SIM_LOCK.acquire(blocking=False):
        raise HTTPException(
            429,
            "Simulación en curso — espera unos segundos e inténtalo otra vez.",
        )
    try:
        yield
    finally:
        _HEAVY_SIM_LOCK.release()
        gc.collect()


def _cached_validation_result(req: LiquiditySweepRequest) -> dict | None:
    """Periodo 2022–2024 precalculado (PythonAnywhere free no llega en 60 s)."""
    if (
        req.symbol == "EURUSD"
        and req.timeframe == "M5"
        and req.period_start == "2022-01-01"
        and req.period_end == "2024-10-30"
        and _VALIDATE_CACHE.is_file()
    ):
        data = json.loads(_VALIDATE_CACHE.read_text(encoding="utf-8"))
        data["cached"] = True
        if req.trades_limit > 0 and len(data.get("trades", [])) > req.trades_limit:
            data["trades"] = data["trades"][-req.trades_limit :]
        data["equity_curve"] = _downsample(data.get("equity_curve", []), req.equity_points)
        return data
    return None


class FondeoBacktestRequest(BaseModel):
    symbol: str = "EURUSD"
    timeframe: str = "M5"
    period_start: Optional[str] = Field(None, description="ISO date, ej 2017-01-03")
    period_end: Optional[str] = Field(None, description="ISO date, ej 2022-03-31")
    fast_period: int = Field(9, ge=2, le=50)
    slow_period: int = Field(20, ge=3, le=200)
    risk_pct: float = Field(2.1, ge=0.5, le=10)
    tp_ratio: float = Field(1.0, ge=0.5, le=5)
    sess_start: int = Field(800, ge=0, le=2359)
    sess_end: int = Field(1000, ge=0, le=2359)
    max_trades_per_day: int = Field(2, ge=1, le=10)
    initial_balance: float = Field(5000.0, gt=0)
    mm_risk_pct: Optional[float] = Field(None, description="Money mgmt %; default = risk_pct")
    slippage_pips: float = Field(2.0, ge=0, le=20)
    allow_long: bool = True
    allow_short: bool = True
    broker_utc_offset_hours: int = Field(0, ge=-12, le=14, description="Offset UTC→hora broker")
    trades_limit: int = Field(500, ge=0)
    equity_points: int = Field(300, ge=0)
    commission_usd: float = Field(5.0, ge=0, le=50, description="Comisión round-trip por trade/cuenta (hedge)")


class FondeoGridRequest(FondeoBacktestRequest):
    grid: dict[str, list[float | int]] = Field(
        default_factory=lambda: {"risk_pct": [1.0, 2.1, 4.0], "max_trades_per_day": [1, 2]},
    )
    max_combinations: int = Field(50, ge=1, le=200)


class LiquiditySweepRequest(BaseModel):
    symbol: str = "EURUSD"
    timeframe: str = "M5"
    period_start: Optional[str] = Field(None, description="ISO date, ej 2017-01-03")
    period_end: Optional[str] = Field(None, description="ISO date, ej 2022-03-31")
    lookback_bars: int = Field(24, ge=6, le=120)
    equal_tolerance_pips: float = Field(3.0, ge=0, le=20)
    sess_start: int = Field(700, ge=0, le=2359)
    sess_end: int = Field(1400, ge=0, le=2359)
    risk_pct: float = Field(2.1, ge=0.5, le=10)
    tp_ratio: float = Field(1.5, ge=0.5, le=5)
    sl_buffer_pips: float = Field(2.0, ge=0, le=20)
    max_trades_per_day: int = Field(2, ge=1, le=10)
    initial_balance: float = Field(5000.0, gt=0)
    mm_risk_pct: Optional[float] = None
    broker_utc_offset_hours: int = Field(7, ge=-12, le=14)
    allow_long: bool = True
    allow_short: bool = True
    equity_sample_bars: int = Field(12, ge=1, le=96)
    trades_limit: int = Field(500, ge=0)
    equity_points: int = Field(300, ge=0)
    use_regime_filter: bool = False
    adx_period: int = Field(14, ge=5, le=50)
    adx_min: float = Field(0.0, ge=0, le=60)
    adx_max: float = Field(0.0, ge=0, le=80)
    atr_period: int = Field(14, ge=5, le=50)
    min_atr_pips: float = Field(0.0, ge=0, le=50)
    max_atr_pips: float = Field(0.0, ge=0, le=100)


class LiquiditySweepMonthlyRequest(LiquiditySweepRequest):
    year: int = Field(2026, ge=2000, le=2100)
    month_from: int = Field(1, ge=1, le=12)
    month_to: int = Field(12, ge=1, le=12)
    include_ytd: bool = Field(True, description="Incluir fila acumulada desde 1 ene del año hasta fin de datos")


class LiquiditySweepChartRequest(LiquiditySweepRequest):
    max_bars: int = Field(1200, ge=100, le=5000)
    max_period_days: int = Field(45, ge=1, le=90)


def _to_config(req: FondeoBacktestRequest) -> FondeoConfig:
    if req.slow_period <= req.fast_period:
        raise HTTPException(400, "slow_period debe ser mayor que fast_period")
    return FondeoConfig(
        fast_period=req.fast_period,
        slow_period=req.slow_period,
        risk_pct=req.risk_pct,
        tp_ratio=req.tp_ratio,
        sess_start=req.sess_start,
        sess_end=req.sess_end,
        max_trades_per_day=req.max_trades_per_day,
        initial_balance=req.initial_balance,
        mm_risk_pct=req.mm_risk_pct if req.mm_risk_pct is not None else req.risk_pct,
        slippage_pips=req.slippage_pips,
        allow_long=req.allow_long,
        allow_short=req.allow_short,
        broker_utc_offset_hours=req.broker_utc_offset_hours,
    )


def _to_liq_config(req: LiquiditySweepRequest) -> LiquiditySweepConfig:
    return LiquiditySweepConfig(
        lookback_bars=req.lookback_bars,
        equal_tolerance_pips=req.equal_tolerance_pips,
        sess_start=req.sess_start,
        sess_end=req.sess_end,
        risk_pct=req.risk_pct,
        tp_ratio=req.tp_ratio,
        sl_buffer_pips=req.sl_buffer_pips,
        max_trades_per_day=req.max_trades_per_day,
        initial_balance=req.initial_balance,
        mm_risk_pct=req.mm_risk_pct if req.mm_risk_pct is not None else req.risk_pct,
        broker_utc_offset_hours=req.broker_utc_offset_hours,
        allow_long=req.allow_long,
        allow_short=req.allow_short,
        equity_sample_bars=req.equity_sample_bars,
        use_regime_filter=req.use_regime_filter,
        adx_period=req.adx_period,
        adx_min=req.adx_min,
        adx_max=req.adx_max,
        atr_period=req.atr_period,
        min_atr_pips=req.min_atr_pips,
        max_atr_pips=req.max_atr_pips,
    )


def _ws_cfg_from_liq(req: LiquiditySweepRequest) -> FondeoConfig:
    """Config mínima para evaluate_ws_classic (reglas WS)."""
    return FondeoConfig(
        risk_pct=req.risk_pct,
        max_trades_per_day=req.max_trades_per_day,
        initial_balance=req.initial_balance,
        broker_utc_offset_hours=req.broker_utc_offset_hours,
        equity_sample_bars=req.equity_sample_bars,
    )


def _load_liq_data(req: LiquiditySweepRequest) -> pd.DataFrame:
    try:
        bars = ForexDataAdapter.load_bars(
            symbol=req.symbol,
            timeframe=req.timeframe,
            start=req.period_start,
            end=req.period_end,
        )
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc
    if bars.empty:
        dr = ForexDataAdapter.data_range(req.symbol, req.timeframe)
        if dr.get("available"):
            raise HTTPException(
                404,
                f"Sin barras entre {req.period_start} y {req.period_end}. "
                f"Datos disponibles: {dr['date_from']} → {dr['date_to']} ({dr['rows']:,} barras). "
                f"Ajusta las fechas o sube un CSV más reciente.",
            )
        raise HTTPException(
            404,
            f"No hay CSV para {req.symbol}_{req.timeframe}. Sube datos con el botón «Subir CSV M5».",
        )
    return bars


def _simulate_liq_windows(
    bars: pd.DataFrame,
    liq_cfg: LiquiditySweepConfig,
    ws_cfg: FondeoConfig,
    window_days: int,
    start: str = "2017-01-03",
    end: str = "2021-09-01",
    step: str = "MS",
) -> dict:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    starts = pd.date_range(start, end, freq=step, tz="UTC")
    passed = total = 0
    days_list: list[int] = []
    for s in starts:
        e = s + pd.Timedelta(days=window_days)
        chunk = df[(df["timestamp"] >= s) & (df["timestamp"] < e)]
        if len(chunk) < 400:
            continue
        total += 1
        r = run_liquidity_sweep(chunk, liq_cfg)
        ev = evaluate_ws_classic(r, ws_cfg)
        if ev["checks"]["pass_all"]:
            passed += 1
            if ev["days_to_meta"] is not None:
                days_list.append(ev["days_to_meta"])
    med = sorted(days_list)[len(days_list) // 2] if days_list else None
    rate = round(100.0 * passed / total, 1) if total else 0.0
    return {
        "pass_rate_pct": rate,
        "passed": passed,
        "attempts": total,
        "median_days_to_meta": med,
    }


def _liq_payload(result, req: LiquiditySweepRequest, bars_len: int, liq_cfg: LiquiditySweepConfig) -> dict:
    ws_cfg = _ws_cfg_from_liq(req)
    payload = result.to_dict()
    payload["bars_used"] = bars_len
    payload["data_source"] = str(ForexDataAdapter.cache_path(req.symbol, req.timeframe))
    if req.trades_limit > 0 and len(payload["trades"]) > req.trades_limit:
        payload["trades"] = payload["trades"][-req.trades_limit:]
    payload["equity_curve"] = _downsample(payload["equity_curve"], req.equity_points)
    by_year: dict[str, dict] = {}
    for t in result.trades:
        year = t.timestamp[:4]
        bucket = by_year.setdefault(year, {"trades": 0, "wins": 0, "pnl": 0.0})
        bucket["trades"] += 1
        bucket["pnl"] += t.pnl
        if t.is_winner:
            bucket["wins"] += 1
    payload["by_year"] = [
        {
            "year": y,
            "trades": v["trades"],
            "wins": v["wins"],
            "win_rate_pct": round(100 * v["wins"] / v["trades"], 1) if v["trades"] else 0,
            "pnl": round(v["pnl"], 2),
        }
        for y, v in sorted(by_year.items())
    ]
    payload["ws_eval"] = evaluate_ws_classic(result, ws_cfg)
    payload["strategy_config"] = liq_cfg.to_dict()
    return payload


def _downsample(points: list, target: int) -> list:
    if target <= 0 or len(points) <= target:
        return points
    step = len(points) / target
    out = [points[int(i * step)] for i in range(target)]
    if out[-1] != points[-1]:
        out.append(points[-1])
    return out


def _period_days(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    s = pd.Timestamp(start, tz="UTC")
    e = pd.Timestamp(end, tz="UTC")
    return max(1, int((e - s).days) + 1)


def _json_native(value: Any) -> Any:
    """Convierte numpy scalars a tipos nativos serializables en JSON."""
    if isinstance(value, dict):
        return {k: _json_native(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_native(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _bars_for_chart(df: pd.DataFrame, max_bars: int, pin_iso_times: list[str]) -> list[dict]:
    if df.empty:
        return []
    must_keep: set[int] = set()
    for iso in pin_iso_times:
        pt = pd.Timestamp(iso)
        if pt.tzinfo is None:
            pt = pt.tz_localize("UTC")
        idx = int((df["timestamp"] - pt).abs().argmin())
        for j in range(max(0, idx - 4), min(len(df), idx + 5)):
            must_keep.add(j)

    if len(df) <= max_bars:
        indices = list(range(len(df)))
    else:
        indices_set = set(must_keep)
        budget = max_bars - len(indices_set)
        if budget > 0:
            step = len(df) / budget
            i = 0.0
            while int(i) < len(df) and len(indices_set) < max_bars:
                indices_set.add(int(i))
                i += step
        indices = sorted(indices_set)

    out: list[dict] = []
    for i in indices:
        row = df.iloc[i]
        out.append(
            {
                "t": row["timestamp"].isoformat(),
                "o": round(float(row["open"]), 5),
                "h": round(float(row["high"]), 5),
                "l": round(float(row["low"]), 5),
                "c": round(float(row["close"]), 5),
            }
        )
    return out


def _trade_markers(result) -> list[dict]:
    markers: list[dict] = []
    for t in result.trades:
        extra = t.extra or {}
        markers.append(
            {
                "entry_time": extra.get("entry_time") or t.timestamp,
                "exit_time": t.timestamp,
                "direction": t.direction,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "sl": extra.get("sl"),
                "tp": extra.get("tp"),
                "pnl": t.pnl,
                "won": t.is_winner,
                "reason": extra.get("reason"),
            }
        )
    return markers


def _load_data(req: FondeoBacktestRequest) -> pd.DataFrame:
    try:
        return ForexDataAdapter.load_bars(
            symbol=req.symbol,
            timeframe=req.timeframe,
            start=req.period_start,
            end=req.period_end,
        )
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/data-info")
def data_info() -> dict:
    return ForexDataAdapter.info()


@router.get("/data-range")
def data_range(symbol: str = "EURUSD", timeframe: str = "M5") -> dict:
    return ForexDataAdapter.data_range(symbol, timeframe)


@router.post("/run")
def run_backtest(req: FondeoBacktestRequest) -> dict:
    _check_period_limit(req.period_start, req.period_end)
    with _heavy_sim_slot():
        cfg = _to_config(req)
        bars = _load_data(req)
        if bars.empty:
            raise HTTPException(404, "Sin barras en el rango seleccionado")

        ps = pd.to_datetime(req.period_start, utc=True) if req.period_start else None
        pe = pd.to_datetime(req.period_end, utc=True) if req.period_end else None
        result = run_fondeo_backtest(bars, cfg, symbol=req.symbol, period_start=ps, period_end=pe)
        payload = result.to_dict()
        payload["bars_used"] = len(bars)
        payload["data_source"] = str(ForexDataAdapter.cache_path(req.symbol, req.timeframe))

        if req.trades_limit > 0 and len(payload["trades"]) > req.trades_limit:
            payload["trades"] = payload["trades"][-req.trades_limit:]
        payload["equity_curve"] = _downsample(payload["equity_curve"], req.equity_points)

        by_year: dict[str, dict] = {}
        for t in result.trades:
            year = t.timestamp[:4]
            bucket = by_year.setdefault(year, {"trades": 0, "wins": 0, "pnl": 0.0})
            bucket["trades"] += 1
            bucket["pnl"] += t.pnl
            if t.is_winner:
                bucket["wins"] += 1
        payload["by_year"] = [
            {
                "year": y,
                "trades": v["trades"],
                "wins": v["wins"],
                "win_rate_pct": round(100 * v["wins"] / v["trades"], 1) if v["trades"] else 0,
                "pnl": round(v["pnl"], 2),
            }
            for y, v in sorted(by_year.items())
        ]
        payload["ws_eval"] = evaluate_ws_classic(result, cfg)
        return payload


@router.post("/grid-search")
def grid_search(req: FondeoGridRequest) -> dict:
    _reject_if_online_only_local("Grid search")
    _check_period_limit(req.period_start, req.period_end)
    with _heavy_sim_slot():
        bars = _load_data(req)
        if bars.empty:
            raise HTTPException(404, "Sin barras en el rango seleccionado")

        base = _to_config(req)
        ps = pd.to_datetime(req.period_start, utc=True) if req.period_start else None
        pe = pd.to_datetime(req.period_end, utc=True) if req.period_end else None

        param_names = list(req.grid.keys())
        value_lists = [req.grid[k] for k in param_names]
        combos = list(itertools.product(*value_lists))[: req.max_combinations]

        results = []
        for combo in combos:
            overrides = dict(zip(param_names, combo))
            cfg_dict = base.to_dict()
            cfg_dict.update(overrides)
            if cfg_dict["slow_period"] <= cfg_dict["fast_period"]:
                continue
            cfg = FondeoConfig(**{k: cfg_dict[k] for k in FondeoConfig.__dataclass_fields__})
            r = run_fondeo_backtest(bars, cfg, symbol=req.symbol, period_start=ps, period_end=pe)
            m = r.metrics
            results.append({
                "params": overrides,
                "n_trades": m["n_trades"],
                "win_rate_pct": m["win_rate_pct"],
                "total_pnl": r.total_pnl,
                "total_pnl_pct": r.total_pnl_pct,
                "max_drawdown_pct": m["max_drawdown_pct"],
                "profit_factor": m["profit_factor"],
            })

        results.sort(key=lambda x: (x["profit_factor"], x["total_pnl"]), reverse=True)
        return {
            "results": results,
            "best": results[0] if results else None,
            "param_names": param_names,
            "combinations_tested": len(results),
        }


@router.post("/ws-eval-sim")
def ws_eval_sim(req: FondeoBacktestRequest) -> dict:
    """Simula arranques mensuales de eval WS (ventanas 14 y 30 días)."""
    _check_period_limit(req.period_start, req.period_end)
    with _heavy_sim_slot():
        cfg = _to_config(req)
        bars = _load_data(req)
        if bars.empty:
            raise HTTPException(404, "Sin barras en el rango seleccionado")
        ps = pd.to_datetime(req.period_start, utc=True) if req.period_start else None
        pe = pd.to_datetime(req.period_end, utc=True) if req.period_end else None
        if ps is not None:
            bars = bars[bars["timestamp"] >= ps]
        if pe is not None:
            bars = bars[bars["timestamp"] <= pe]
        full = run_fondeo_backtest(bars, cfg, symbol=req.symbol)
        w14 = simulate_eval_windows(bars, cfg, window_days=14, step="2MS")
        w30 = simulate_eval_windows(bars, cfg, window_days=30, step="2MS")
        return {
            "ws_eval": evaluate_ws_classic(full, cfg),
            "windows": {
                "14d": {
                    "pass_rate_pct": w14.pass_rate_pct,
                    "passed": w14.passed,
                    "attempts": w14.attempts,
                    "median_days_to_meta": w14.median_days_to_meta,
                },
                "30d": {
                    "pass_rate_pct": w30.pass_rate_pct,
                    "passed": w30.passed,
                    "attempts": w30.attempts,
                    "median_days_to_meta": w30.median_days_to_meta,
                },
            },
        }


@router.get("/hedge-report")
def hedge_report() -> dict:
    """Último reporte hedge guardado por scripts/hedge_lab_run.py."""
    path = ForexDataAdapter.cache_path("EURUSD", "M5").parent / "hedge_lab_report.json"
    report_path = path.parent / "hedge_lab_report.json"
    if not report_path.is_file():
        raise HTTPException(404, "Sin reporte — ejecuta POST /hedge-lab-run")
    import json
    return json.loads(report_path.read_text(encoding="utf-8"))


@router.post("/hedge-lab-run")
def hedge_lab_run(req: FondeoBacktestRequest) -> dict:
    """Ejecuta backtest hedge completo (ventanas 7–60d) y guarda reporte."""
    _reject_if_online_only_local("Backtest hedge completo")
    _check_period_limit(req.period_start, req.period_end)
    with _heavy_sim_slot():
        cfg = _to_config(req)
        bars = _load_data(req)
        if bars.empty:
            raise HTTPException(404, "Sin barras en el rango seleccionado")
        ps = pd.to_datetime(req.period_start, utc=True) if req.period_start else None
        pe = pd.to_datetime(req.period_end, utc=True) if req.period_end else None
        if ps is not None:
            bars = bars[bars["timestamp"] >= ps]
        if pe is not None:
            bars = bars[bars["timestamp"] <= pe]

        windows: dict = {}
        for days in (7, 14, 30, 60):
            w = simulate_hedged_windows(bars, cfg, window_days=days, step="2MS", commission_usd=req.commission_usd)
            windows[f"{days}d"] = {
                "pair_wins": w.pair_wins,
                "attempts": w.attempts,
                "pass_rate_pct": w.pass_rate_pct,
                "median_days": w.median_days,
                "a_wins": w.a_wins,
                "b_wins": w.b_wins,
                "both_fail": w.both_fail,
            }

        full = run_hedged_backtest(bars, cfg, commission_usd=req.commission_usd, stop_at_meta=False)
        fd = full.to_dict()
        report = {
            "config": cfg.to_dict(),
            "bars": len(bars),
            "windows": windows,
            "full_period": {
                "outcome": full.outcome,
                "account_a_pnl": fd["account_a"]["total_pnl"],
                "account_b_pnl": fd["account_b"]["total_pnl"],
                "account_a_dd": fd["account_a"]["ws_eval"]["static_dd_pct"],
                "account_b_dd": fd["account_b"]["ws_eval"]["static_dd_pct"],
            },
        }
        report_path = ForexDataAdapter.cache_path("EURUSD", "M5").parent / "hedge_lab_report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report


@router.post("/hedge-sim")
def hedge_sim(req: FondeoBacktestRequest) -> dict:
    """Simula par hedge: cuenta A natural + cuenta B espejo (curso HobbyCode)."""
    _check_period_limit(req.period_start, req.period_end)
    with _heavy_sim_slot():
        cfg = _to_config(req)
        bars = _load_data(req)
        if bars.empty:
            raise HTTPException(404, "Sin barras en el rango seleccionado")
        ps = pd.to_datetime(req.period_start, utc=True) if req.period_start else None
        pe = pd.to_datetime(req.period_end, utc=True) if req.period_end else None
        if ps is not None:
            bars = bars[bars["timestamp"] >= ps]
        if pe is not None:
            bars = bars[bars["timestamp"] <= pe]
        pair = run_hedged_backtest(bars, cfg, commission_usd=req.commission_usd)
        w7 = simulate_hedged_windows(bars, cfg, window_days=7, step="2MS", commission_usd=req.commission_usd)
        w14 = simulate_hedged_windows(bars, cfg, window_days=14, step="2MS", commission_usd=req.commission_usd)
        w30 = simulate_hedged_windows(bars, cfg, window_days=30, step="2MS", commission_usd=req.commission_usd)
        payload = pair.to_dict()
        payload["windows"] = {
            "7d": {
                "pass_rate_pct": w7.pass_rate_pct,
                "pair_wins": w7.pair_wins,
                "attempts": w7.attempts,
                "median_days": w7.median_days,
                "a_wins": w7.a_wins,
                "b_wins": w7.b_wins,
                "both_fail": w7.both_fail,
            },
            "14d": {
                "pass_rate_pct": w14.pass_rate_pct,
                "pair_wins": w14.pair_wins,
                "attempts": w14.attempts,
                "median_days": w14.median_days,
                "a_wins": w14.a_wins,
                "b_wins": w14.b_wins,
                "both_fail": w14.both_fail,
            },
            "30d": {
                "pass_rate_pct": w30.pass_rate_pct,
                "pair_wins": w30.pair_wins,
                "attempts": w30.attempts,
                "median_days": w30.median_days,
                "a_wins": w30.a_wins,
                "b_wins": w30.b_wins,
                "both_fail": w30.both_fail,
            },
        }
        payload["bars_used"] = len(bars)
        return payload


@router.post("/liquidity-sweep/run")
def run_liquidity_sweep_backtest(req: LiquiditySweepRequest) -> dict:
    """Backtest Liquidity Sweep (SMC) — mejor candidata del lab para eval WS."""
    _check_period_limit(req.period_start, req.period_end)
    cached = _cached_validation_result(req)
    if cached is not None:
        return cached
    with _heavy_sim_slot():
        liq_cfg = _to_liq_config(req)
        bars = _load_liq_data(req)
        if bars.empty:
            raise HTTPException(404, "Sin barras en el rango seleccionado")
        result = run_liquidity_sweep(bars, liq_cfg, symbol=req.symbol)
        return _liq_payload(result, req, len(bars), liq_cfg)


@router.post("/liquidity-sweep/chart")
def liquidity_sweep_chart(req: LiquiditySweepChartRequest) -> dict:
    """Velas EURUSD + marcadores de entrada (compra/venta) para un periodo corto."""
    days = _period_days(req.period_start, req.period_end)
    if days is not None and days > req.max_period_days:
        raise HTTPException(
            400,
            f"Periodo demasiado largo ({days} días). Máximo {req.max_period_days} días para el gráfico.",
        )

    liq_cfg = _to_liq_config(req)
    bars = _load_liq_data(req)
    if bars.empty:
        raise HTTPException(404, "Sin barras en el rango seleccionado")

    result = run_liquidity_sweep(bars, liq_cfg, symbol=req.symbol)
    markers = _trade_markers(result)
    pin_times = [m["entry_time"] for m in markers]
    chart_bars = _bars_for_chart(bars, req.max_bars, pin_times)

    return {
        "symbol": req.symbol,
        "timeframe": req.timeframe,
        "period_start": req.period_start,
        "period_end": req.period_end,
        "bars": chart_bars,
        "markers": markers,
        "total_bars_in_period": len(bars),
        "trades_in_period": len(markers),
    }


@router.post("/liquidity-sweep/ws-eval-sim")
def liquidity_sweep_ws_eval_sim(req: LiquiditySweepRequest) -> dict:
    """Simula arranques mensuales de eval WS con Liquidity Sweep."""
    liq_cfg = _to_liq_config(req)
    ws_cfg = _ws_cfg_from_liq(req)
    bars = _load_liq_data(req)
    if bars.empty:
        raise HTTPException(404, "Sin barras en el rango seleccionado")
    ps = pd.to_datetime(req.period_start, utc=True) if req.period_start else None
    pe = pd.to_datetime(req.period_end, utc=True) if req.period_end else None
    if ps is not None:
        bars = bars[bars["timestamp"] >= ps]
    if pe is not None:
        bars = bars[bars["timestamp"] <= pe]
    full = run_liquidity_sweep(bars, liq_cfg, symbol=req.symbol)
    w14 = _simulate_liq_windows(bars, liq_cfg, ws_cfg, window_days=14, step="2MS")
    w30 = _simulate_liq_windows(bars, liq_cfg, ws_cfg, window_days=30, step="2MS")
    return {
        "ws_eval": evaluate_ws_classic(full, ws_cfg),
        "windows": {"14d": w14, "30d": w30},
    }


def _month_breakdown_row(
    label: str,
    start: str,
    end: str,
    bars: pd.DataFrame,
    liq_cfg: LiquiditySweepConfig,
    ws_cfg: FondeoConfig,
    *,
    kind: str = "month",
) -> dict:
    chunk = bars[(bars["timestamp"] >= start) & (bars["timestamp"] <= end + " 23:59:59")].reset_index(drop=True)
    if len(chunk) < 50:
        return {
            "label": label,
            "kind": kind,
            "period_start": start,
            "period_end": end,
            "bars": len(chunk),
            "error": "insufficient_data",
        }
    result = run_liquidity_sweep(chunk, liq_cfg, symbol="EURUSD")
    ev = evaluate_ws_classic(result, ws_cfg)
    checks = ev["checks"]
    fail_reasons = [
        k.replace("pass_", "")
        for k, ok in checks.items()
        if k.startswith("pass_") and k != "pass_all" and not ok
    ]
    return _json_native({
        "label": label,
        "kind": kind,
        "period_start": start,
        "period_end": end,
        "data_to": chunk["timestamp"].iloc[-1].isoformat(),
        "bars": len(chunk),
        "trades": result.metrics["n_trades"],
        "win_rate_pct": result.metrics["win_rate_pct"],
        "total_pnl": round(float(result.total_pnl), 2),
        "total_pnl_pct": round(float(result.total_pnl_pct), 2),
        "static_dd_pct": ev["static_dd_pct"],
        "max_daily_loss_pct": ev["max_daily_loss_pct"],
        "trading_days": ev["trading_days"],
        "days_to_meta": ev.get("days_to_meta"),
        "pass_eval": bool(checks["pass_all"]),
        "checks": checks,
        "fail_reasons": fail_reasons,
    })


@router.post("/liquidity-sweep/monthly-breakdown")
def liquidity_sweep_monthly_breakdown(req: LiquiditySweepMonthlyRequest) -> dict:
    """Backtest calendario mes a mes + acumulado YTD (config actual del lab)."""
    if req.month_to < req.month_from:
        raise HTTPException(400, "month_to debe ser >= month_from")

    liq_cfg = _to_liq_config(req)
    ws_cfg = _ws_cfg_from_liq(req)
    dr = ForexDataAdapter.data_range(req.symbol, req.timeframe)
    if not dr.get("available"):
        raise HTTPException(404, f"Sin CSV para {req.symbol}_{req.timeframe}")

    data_end = pd.Timestamp(dr["date_to"], tz="UTC")
    month_names = [
        "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]
    rows: list[dict] = []

    for m in range(req.month_from, req.month_to + 1):
        start = pd.Timestamp(req.year, m, 1, tz="UTC")
        if start > data_end:
            continue
        end_day = pd.Timestamp(req.year, m, 1, tz="UTC") + pd.offsets.MonthEnd(0)
        end = min(end_day, data_end)
        month_start = start.strftime("%Y-%m-%d")
        month_end = end.strftime("%Y-%m-%d")
        try:
            month_bars = ForexDataAdapter.load_bars(
                req.symbol,
                req.timeframe,
                start=month_start,
                end=month_end,
            )
        except RuntimeError:
            rows.append({
                "label": f"{month_names[m]} {req.year}",
                "kind": "month",
                "period_start": month_start,
                "period_end": month_end,
                "error": "no_data",
            })
            continue
        rows.append(_month_breakdown_row(
            f"{month_names[m]} {req.year}",
            month_start,
            month_end,
            month_bars,
            liq_cfg,
            ws_cfg,
        ))

    ytd_row = None
    if req.include_ytd:
        ytd_start = pd.Timestamp(req.year, 1, 1, tz="UTC")
        if ytd_start <= data_end:
            ytd_start_s = ytd_start.strftime("%Y-%m-%d")
            ytd_end_s = data_end.strftime("%Y-%m-%d")
            try:
                ytd_bars = ForexDataAdapter.load_bars(
                    req.symbol,
                    req.timeframe,
                    start=ytd_start_s,
                    end=ytd_end_s,
                )
            except RuntimeError:
                ytd_bars = pd.DataFrame()
            if not ytd_bars.empty:
                ytd_row = _month_breakdown_row(
                    f"Ene → hoy ({data_end.strftime('%Y-%m-%d')})",
                    ytd_start_s,
                    ytd_end_s,
                    ytd_bars,
                    liq_cfg,
                    ws_cfg,
                    kind="ytd",
                )

    return {
        "strategy": "liquidity_sweep",
        "symbol": req.symbol,
        "timeframe": req.timeframe,
        "year": req.year,
        "data_range": dr,
        "months": rows,
        "ytd": ytd_row,
        "strategy_config": liq_cfg.to_dict(),
    }


@router.get("/liquidity-sweep/regime-compare")
def liquidity_sweep_regime_compare_cached() -> dict:
    """Último resultado scripts/eval_regime_compare.py (192 variantes ADX/ATR)."""
    path = ForexDataAdapter.cache_path("EURUSD", "M5").parent / "liq_sweep_regime_compare.json"
    if not path.is_file():
        raise HTTPException(404, "Sin compare — ejecuta scripts/eval_regime_compare.py")
    import json
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/upload-csv")
async def upload_csv(
    file: UploadFile = File(...),
    symbol: str = "EURUSD",
    timeframe: str = "M5",
) -> dict:
    content = await file.read()
    if not content:
        raise HTTPException(400, "Archivo vacio")
    try:
        df = ForexDataAdapter.load_from_upload(content)
    except Exception as exc:
        raise HTTPException(400, f"CSV invalido: {exc}") from exc
    path = ForexDataAdapter.save_cache(df, symbol, timeframe)
    return {
        "ok": True,
        "path": str(path),
        "rows": len(df),
        "from": df["timestamp"].iloc[0].isoformat(),
        "to": df["timestamp"].iloc[-1].isoformat(),
    }
