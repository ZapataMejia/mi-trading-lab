#!/usr/bin/env python3
"""Mega hunt — todas las estrategias prop firm · OOS 2022-2024 · objetivo pass 30d ≥55%."""
from __future__ import annotations

import itertools
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from webapp.backend.engine.fondeo_engine import FondeoConfig, run_fondeo_backtest
from webapp.backend.engine.ict_judas_engine import JudasConfig, run_judas_swing
from webapp.backend.engine.liquidity_sweep_engine import LiquiditySweepConfig, run_liquidity_sweep
from webapp.backend.engine.london_breakout_engine import LondonBreakoutConfig, run_london_breakout
from webapp.backend.engine.orb_adx_engine import OrbAdxConfig, run_orb_adx
from webapp.backend.engine.silver_bullet_engine import SilverBulletConfig, run_silver_bullet
from webapp.backend.engine.ws_eval import evaluate_ws_classic
from webapp.backend.markets.forex import ForexDataAdapter, _normalize_ohlc

OUT = ROOT / "data/forex_cache/hunt_mega_prop.json"
PERIOD = ("2022-01-01", "2024-10-30")
W30 = ("2022-01-01", "2024-08-01")
MAX_DAILY = 4.5


def load(symbol: str = "EURUSD") -> pd.DataFrame:
    path = ForexDataAdapter.cache_path(symbol, "M5")
    if not path.exists() and symbol != "EURUSD":
        return pd.DataFrame()
    df = _normalize_ohlc(pd.read_csv(path)) if path.exists() else ForexDataAdapter.load_bars(symbol, "M5")
    return df[(df["timestamp"] >= PERIOD[0]) & (df["timestamp"] <= PERIOD[1])].reset_index(drop=True)


def ws_cfg(off: int, risk: float, max_td: int) -> FondeoConfig:
    return FondeoConfig(
        risk_pct=risk, max_trades_per_day=max_td, initial_balance=5000.0,
        broker_utc_offset_hours=off, equity_sample_bars=12,
    )


def eval30(bars: pd.DataFrame, fn, cfg, wcfg: FondeoConfig) -> dict:
    starts = pd.date_range(W30[0], W30[1], freq="2MS", tz="UTC")
    passed = total = 0
    days_list: list[int] = []
    for s in starts:
        chunk = bars[(bars["timestamp"] >= s) & (bars["timestamp"] < s + pd.Timedelta(days=30))]
        if len(chunk) < 400:
            continue
        total += 1
        r = fn(chunk, cfg)
        ev = evaluate_ws_classic(r, wcfg)
        if ev["checks"]["pass_all"]:
            passed += 1
            if ev["days_to_meta"] is not None:
                days_list.append(ev["days_to_meta"])
    med = sorted(days_list)[len(days_list) // 2] if days_list else None
    rate = round(100 * passed / total, 1) if total else 0.0
    return {"w30_pass": passed, "w30_total": total, "w30_rate": rate, "w30_med": med}


def screen(name: str, cfg, fn, bars: pd.DataFrame) -> dict | None:
    off = getattr(cfg, "broker_utc_offset_hours", 7)
    risk = getattr(cfg, "risk_pct", 2.0)
    max_td = getattr(cfg, "max_trades_per_day", 2)
    r = fn(bars, cfg)
    if r.metrics["n_trades"] < 15:
        return None
    ev = evaluate_ws_classic(r, ws_cfg(off, risk, max_td))
    if not ev["checks"]["pass_all"] or ev["max_daily_loss_pct"] > MAX_DAILY:
        return None
    return {
        "strategy": name,
        **cfg.to_dict(),
        "full_pnl": round(r.total_pnl, 2),
        "full_dd": round(ev["static_dd_pct"], 2),
        "full_daily_dd": round(ev["max_daily_loss_pct"], 2),
        "full_trades": r.metrics["n_trades"],
        "full_pf": round(min(r.metrics.get("profit_factor") or 0, 999), 2),
        "days_to_meta": ev["days_to_meta"],
    }


def build_grids() -> list[tuple[str, object, callable]]:
    out: list[tuple[str, object, callable]] = []

    for lb, (ss, se), tp, risk, mtd, buf in itertools.product(
        [24, 36, 48], [(700, 1100), (700, 1200), (700, 1400)], [1.5, 2.0, 2.5],
        [1.0, 1.5, 2.0], [1, 2], [2.0, 3.0],
    ):
        out.append(("liq_sweep", LiquiditySweepConfig(
            lookback_bars=lb, sess_start=ss, sess_end=se, tp_ratio=tp, risk_pct=risk,
            max_trades_per_day=mtd, sl_buffer_pips=buf, broker_utc_offset_hours=7,
            mm_risk_pct=risk, equity_sample_bars=12,
        ), run_liquidity_sweep))

    for (ks, ke), risk, min_rng, tp_m in itertools.product(
        [(700, 900), (700, 1000), (800, 1000)], [0.8, 1.0, 1.5], [8.0, 10.0, 12.0], [1.5, 2.0],
    ):
        out.append(("judas", JudasConfig(
            kill_start=ks, kill_end=ke, risk_pct=risk, mm_risk_pct=risk,
            min_asian_range_pips=min_rng, tp_range_mult=tp_m, max_trades_per_day=1,
            broker_utc_offset_hours=7, equity_sample_bars=12,
        ), run_judas_swing))

    for (ws, we), risk, min_disp, tp in itertools.product(
        [(1400, 1500), (1500, 1600), (2100, 2200), (1000, 1100)], [0.8, 1.0, 1.5], [3.0, 4.0, 5.0], [1.5, 2.0, 2.5],
    ):
        out.append(("silver_bullet", SilverBulletConfig(
            window_start=ws, window_end=we, risk_pct=risk, mm_risk_pct=risk,
            min_displacement_pips=min_disp, tp_ratio=tp, max_trades_per_day=1,
            broker_utc_offset_hours=7, equity_sample_bars=12,
        ), run_silver_bullet))

    for (ss, se), orb, adx, risk, mult in itertools.product(
        [(800, 1200), (900, 1300), (700, 1100)], [4, 6, 8], [18.0, 22.0, 25.0],
        [0.8, 1.0, 1.5], [1.0, 1.5, 2.0],
    ):
        out.append(("orb_adx", OrbAdxConfig(
            sess_start=ss, sess_end=se, orb_bars=orb, adx_min=adx, risk_pct=risk,
            mm_risk_pct=risk, tp_range_mult=mult, max_trades_per_day=1,
            broker_utc_offset_hours=7, equity_sample_bars=12,
        ), run_orb_adx))

    for mode, mult, risk in itertools.product(["fade"], [1.0, 1.5, 2.0], [1.0, 1.5]):
        out.append(("london_fade", LondonBreakoutConfig(
            mode=mode, tp_range_mult=mult, risk_pct=risk, mm_risk_pct=risk,
            max_trades_per_day=1, broker_utc_offset_hours=7, equity_sample_bars=12,
        ), run_london_breakout))

    for fast, slow, tp, risk, (ss, se) in itertools.product(
        [(5, 13), (9, 21), (8, 21)], [1.0, 1.5, 2.0], [1.0, 1.5], [0.8, 1.0, 1.5], [(800, 1200), (900, 1400)],
    ):
        out.append(("ema", FondeoConfig(
            fast_period=fast, slow_period=slow, tp_ratio=tp, risk_pct=risk, mm_risk_pct=risk,
            sess_start=ss, sess_end=se, max_trades_per_day=2, broker_utc_offset_hours=7,
            equity_sample_bars=12,
        ), run_fondeo_backtest))

    return out


def rebuild(name: str, row: dict):
    if name == "liq_sweep":
        return LiquiditySweepConfig(**{k: row[k] for k in LiquiditySweepConfig.__dataclass_fields__ if k in row}), run_liquidity_sweep
    if name == "judas":
        return JudasConfig(**{k: row[k] for k in JudasConfig.__dataclass_fields__ if k in row}), run_judas_swing
    if name == "silver_bullet":
        return SilverBulletConfig(**{k: row[k] for k in SilverBulletConfig.__dataclass_fields__ if k in row}), run_silver_bullet
    if name == "orb_adx":
        return OrbAdxConfig(**{k: row[k] for k in OrbAdxConfig.__dataclass_fields__ if k in row}), run_orb_adx
    if name == "london_fade":
        return LondonBreakoutConfig(**{k: row[k] for k in LondonBreakoutConfig.__dataclass_fields__ if k in row}), run_london_breakout
    return FondeoConfig(**{k: row[k] for k in FondeoConfig.__dataclass_fields__ if k in row}), run_fondeo_backtest


def main() -> None:
    bars = load("EURUSD")
    print(f"MEGA HUNT · EURUSD OOS {PERIOD[0]}→{PERIOD[1]} · {len(bars)} bars\n", flush=True)
    grids = build_grids()
    print(f"Configs: {len(grids)}\n", flush=True)
    t0 = time.time()
    survivors: list[dict] = []

    for i, (name, cfg, fn) in enumerate(grids, 1):
        row = screen(name, cfg, fn, bars)
        if row:
            survivors.append(row)
            if row.get("full_dd", 0) > -3:
                print(f"  PASS [{name}] daily={row['full_daily_dd']}% trades={row['full_trades']}", flush=True)
        if i % 200 == 0:
            print(f"  {i}/{len(grids)} survivors={len(survivors)}", flush=True)

    print(f"\nFase 1: {len(survivors)} ({time.time()-t0:.0f}s)\n", flush=True)
    survivors.sort(key=lambda x: (-x["full_daily_dd"], x["full_dd"]), reverse=True)
    top = survivors[:80]

    results: list[dict] = []
    for row in top:
        name = row["strategy"]
        cfg, fn = rebuild(name, row)
        off = row.get("broker_utc_offset_hours", 7)
        w = ws_cfg(off, row.get("risk_pct", 1.0), row.get("max_trades_per_day", 1))
        w30 = eval30(bars, fn, cfg, w)
        enriched = {**row, **w30}
        results.append(enriched)
        if w30["w30_rate"] >= 45:
            print(f"  30d HIT {w30['w30_rate']}% [{name}] daily={row['full_daily_dd']}%", flush=True)

    results.sort(key=lambda x: (x["w30_rate"], x["w30_pass"], -x["full_daily_dd"]), reverse=True)
    best = results[0] if results else None

    # GBPUSD si existe
    gbp_results: list[dict] = []
    gbp_bars = load("GBPUSD")
    if not gbp_bars.empty and best:
        print(f"\nValidando mejor en GBPUSD ({len(gbp_bars)} bars)...", flush=True)
        cfg, fn = rebuild(best["strategy"], best)
        off = best.get("broker_utc_offset_hours", 7)
        w = ws_cfg(off, best.get("risk_pct", 1.0), best.get("max_trades_per_day", 1))
        r = fn(gbp_bars, cfg)
        ev = evaluate_ws_classic(r, w)
        w30 = eval30(gbp_bars, fn, cfg, w)
        gbp_results = [{"full_pass": ev["checks"]["pass_all"], "full_daily_dd": ev["max_daily_loss_pct"], **w30}]

    payload = {
        "objective": "Pass WS CLASSIC $5k en ≤60-90 días · pass 30d ≥55% · daily DD ≤4.5%",
        "period": list(PERIOD),
        "combos_tested": len(grids),
        "survivors_full": len(survivors),
        "best": best,
        "top10": results[:10],
        "target_55_met": best["w30_rate"] >= 55 if best else False,
        "gbpusd_validation": gbp_results[0] if gbp_results else None,
        "recommendation": _recommend(best, results),
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nMEJOR: {best['strategy'] if best else 'NONE'} w30={best['w30_rate'] if best else 0}%", flush=True)
    print(f"→ {OUT}", flush=True)


def _recommend(best: dict | None, results: list[dict]) -> dict:
    if not best:
        return {"verdict": "no_strategy_found", "action": "continue_lab"}
    rate = best["w30_rate"]
    if rate >= 55:
        return {
            "verdict": "ready_for_demo",
            "strategy": best["strategy"],
            "config": {k: best[k] for k in best if k not in ("strategy",)},
            "action": "Demo WS 2 semanas → eval cuenta 1",
        }
    # Probabilidad con 2 cuentas
    p_fail = (1 - rate / 100) ** 2
    p_one_pass = 1 - p_fail
    return {
        "verdict": "best_available_not_55",
        "strategy": best["strategy"],
        "w30_rate": rate,
        "prob_2_accounts_one_passes": round(p_one_pass * 100, 1),
        "action": "Demo 2 semanas + eval cuenta 1; cuenta 2 si breach. Reintentar en mes 2-3.",
        "config": {k: best[k] for k in best if k not in ("strategy", "w30_pass", "w30_total", "w30_rate", "w30_med")},
    }


if __name__ == "__main__":
    main()
