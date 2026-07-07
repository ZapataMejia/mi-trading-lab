"""Simulación reglas WS Funded CLASSIC — cuenta $5k fase 1."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from webapp.backend.engine.fondeo_engine import FondeoConfig, run_fondeo_backtest
from webapp.backend.engine.types import BacktestResult, EquityPoint, Trade

WS_CLASSIC_5K = {
    "plan": "CLASSIC",
    "phase": 1,
    "capital": 5000.0,
    "meta_pct": 8.0,
    "meta_usd": 400.0,
    "max_static_dd_pct": 8.0,
    "daily_dd_pct": 5.0,
    "min_trading_days": 4,
    "max_risk_per_trade_pct": 2.1,
    "max_trades_per_day": 2,
}


def _broker_day(ts: str | pd.Timestamp, offset_hours: int) -> int:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    loc = t + pd.Timedelta(hours=offset_hours)
    return loc.year * 10000 + loc.month * 100 + loc.day


def static_dd_pct(equity: list[EquityPoint], initial: float) -> float:
    if not equity:
        return 0.0
    min_br = min(pt.bankroll for pt in equity)
    return (min_br - initial) / initial * 100.0


def max_daily_loss_pct(equity: list[EquityPoint], offset_hours: int) -> float:
    by_day: dict[int, list[float]] = {}
    for pt in equity:
        by_day.setdefault(_broker_day(pt.timestamp, offset_hours), []).append(pt.bankroll)
    worst = 0.0
    for vals in by_day.values():
        start = vals[0]
        if start <= 0:
            continue
        loss = (start - min(vals)) / start * 100.0
        worst = max(worst, loss)
    return worst


def count_trading_days(trades: list[Trade], offset_hours: int) -> int:
    return len({_broker_day(t.timestamp, offset_hours) for t in trades})


def days_to_meta(equity: list[EquityPoint], initial: float, meta_usd: float) -> int | None:
    if not equity:
        return None
    t0 = pd.Timestamp(equity[0].timestamp)
    if t0.tzinfo is None:
        t0 = t0.tz_localize("UTC")
    for pt in equity:
        if pt.bankroll - initial >= meta_usd:
            ts = pd.Timestamp(pt.timestamp)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            return max(0, (ts - t0).days)
    return None


def evaluate_ws_classic(result: BacktestResult, cfg: FondeoConfig) -> dict[str, Any]:
    """Evalúa un backtest contra reglas WS CLASSIC $5k fase 1."""
    rules = WS_CLASSIC_5K
    initial = cfg.initial_balance
    off = cfg.broker_utc_offset_hours
    dd = static_dd_pct(result.equity_curve, initial)
    daily = max_daily_loss_pct(result.equity_curve, off)
    tdays = count_trading_days(result.trades, off)
    pf = result.metrics.get("profit_factor") or 0.0
    if pf == float("inf"):
        pf = 999.0

    checks = {
        "pass_meta": result.total_pnl >= rules["meta_usd"],
        "pass_static_dd": dd > -rules["max_static_dd_pct"],
        "pass_daily_dd": daily <= rules["daily_dd_pct"],
        "pass_min_days": tdays >= rules["min_trading_days"],
        "pass_pf": pf >= 1.0,
        "pass_risk": cfg.risk_pct <= rules["max_risk_per_trade_pct"],
        "pass_max_trades": cfg.max_trades_per_day <= rules["max_trades_per_day"],
    }
    checks["pass_all"] = all(checks.values())

    return {
        "plan": rules["plan"],
        "phase": rules["phase"],
        "meta_usd": rules["meta_usd"],
        "meta_pct": rules["meta_pct"],
        "static_dd_pct": round(dd, 2),
        "max_daily_loss_pct": round(daily, 2),
        "trading_days": tdays,
        "days_to_meta": days_to_meta(result.equity_curve, initial, rules["meta_usd"]),
        "checks": checks,
        "summary": _summary(checks),
    }


def _summary(checks: dict[str, bool]) -> str:
    if checks["pass_all"]:
        return "PASA eval WS CLASSIC fase 1"
    fails = []
    labels = {
        "pass_meta": "meta +8%",
        "pass_static_dd": "DD estático 8%",
        "pass_daily_dd": "DD diario 5%",
        "pass_min_days": "mín. 4 días trading",
        "pass_pf": "PF ≥ 1",
        "pass_risk": "riesgo ≤ 2.1%",
        "pass_max_trades": "max 2 trades/día",
    }
    for k, label in labels.items():
        if not checks.get(k):
            fails.append(label)
    return "Falla: " + ", ".join(fails)


@dataclass
class WindowSimResult:
    window_days: int
    attempts: int
    passed: int
    pass_rate_pct: float
    median_days_to_meta: int | None


def simulate_eval_windows(
    bars: pd.DataFrame,
    cfg: FondeoConfig,
    window_days: int = 14,
    start: str = "2017-01-03",
    end: str = "2021-06-01",
    step: str = "MS",
) -> WindowSimResult:
    """Arranca eval cada mes; ventana de N días calendario."""
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    starts = pd.date_range(start, end, freq=step, tz="UTC")

    passed = 0
    total = 0
    days_list: list[int] = []

    for s in starts:
        e = s + pd.Timedelta(days=window_days)
        chunk = df[(df["timestamp"] >= s) & (df["timestamp"] < e)]
        if len(chunk) < 500:
            continue
        r = run_fondeo_backtest(chunk, cfg)
        ev = evaluate_ws_classic(r, cfg)
        total += 1
        if ev["checks"]["pass_all"]:
            passed += 1
            if ev["days_to_meta"] is not None:
                days_list.append(ev["days_to_meta"])

    med = sorted(days_list)[len(days_list) // 2] if days_list else None
    rate = round(100.0 * passed / total, 1) if total else 0.0
    return WindowSimResult(window_days, total, passed, rate, med)


def robustness_score(
    bars: pd.DataFrame,
    cfg: FondeoConfig,
    period_start: str = "2017-01-03",
    period_end: str = "2022-03-31",
) -> dict[str, Any]:
    """Puntúa config: backtest largo + ventanas eval 14/30 días."""
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    chunk = df[(df["timestamp"] >= period_start) & (df["timestamp"] <= period_end)]
    full = run_fondeo_backtest(chunk, cfg)
    full_ev = evaluate_ws_classic(full, cfg)

    w14 = simulate_eval_windows(chunk, cfg, window_days=14)
    w30 = simulate_eval_windows(chunk, cfg, window_days=30)

    score = 0.0
    if full_ev["checks"]["pass_all"]:
        score += 2000
    score += w14.pass_rate_pct * 10
    score += w30.pass_rate_pct * 5
    score += full.total_pnl * 0.1
    if full_ev["checks"]["pass_static_dd"]:
        score += 300
    if w14.median_days_to_meta is not None:
        score += max(0, 100 - w14.median_days_to_meta * 5)

    return {
        "score": round(score, 1),
        "full": {
            "trades": full.metrics["n_trades"],
            "pnl": round(full.total_pnl, 2),
            "dd": round(full_ev["static_dd_pct"], 2),
            "pf": round(min(full.metrics["profit_factor"], 999), 2),
            "eval": full_ev,
        },
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
        "config": cfg.to_dict(),
    }
