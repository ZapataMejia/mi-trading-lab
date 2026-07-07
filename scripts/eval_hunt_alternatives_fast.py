#!/usr/bin/env python3
"""Screen rápido alternativas — periodo completo primero."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from webapp.backend.engine.fondeo_engine import FondeoConfig
from webapp.backend.engine.ict_judas_engine import JudasConfig, run_judas_swing
from webapp.backend.engine.liquidity_sweep_engine import LiquiditySweepConfig, run_liquidity_sweep
from webapp.backend.engine.london_breakout_engine import LondonBreakoutConfig, run_london_breakout
from webapp.backend.engine.ws_eval import evaluate_ws_classic, simulate_eval_windows
from webapp.backend.markets.forex import _normalize_ohlc

CSV = ROOT / "data/forex_cache/EURUSD_M5.csv"
OUT = ROOT / "data/forex_cache/hunt_alternatives_fast.json"


def load_bars() -> pd.DataFrame:
    df = _normalize_ohlc(pd.read_csv(CSV))
    return df[(df["timestamp"] >= "2017-01-03") & (df["timestamp"] <= "2022-03-31")].reset_index(drop=True)


def ws_cfg(off: int = 7) -> FondeoConfig:
    return FondeoConfig(broker_utc_offset_hours=off, equity_sample_bars=96)


def main() -> None:
    bars = load_bars()
    candidates: list[dict] = []

    grids: list[tuple[str, object, callable]] = []

    for (as_, ae), (ks, ke), tp_mode, tp_mult, min_rng, off in itertools.product(
        [(0, 700), (0, 600), (100, 700)],
        [(700, 1000), (700, 1100), (800, 1000), (800, 1100)],
        ["asian_opposite", "range_mult"],
        [1.5, 2.0, 2.5],
        [6.0, 8.0, 12.0],
        [0, 7],
    ):
        grids.append(("ict_judas", JudasConfig(
            asian_start=as_, asian_end=ae, kill_start=ks, kill_end=ke,
            tp_mode=tp_mode, tp_range_mult=tp_mult, min_asian_range_pips=min_rng,
            broker_utc_offset_hours=off, equity_sample_bars=96,
        ), run_judas_swing))

    for lb, tp, (ss, se), off in itertools.product(
        [12, 24, 36, 48], [1.5, 2.0, 2.5, 3.0], [(700, 1100), (700, 1400), (800, 1200)], [0, 7],
    ):
        grids.append(("liq_sweep", LiquiditySweepConfig(
            lookback_bars=lb, tp_ratio=tp, sess_start=ss, sess_end=se,
            broker_utc_offset_hours=off, equity_sample_bars=96,
        ), run_liquidity_sweep))

    for mode, (as_, ae), (ts_, te), mult, off in itertools.product(
        ["breakout", "fade"], [(0, 700), (0, 600)], [(700, 1100), (800, 1100)], [1.0, 1.5, 2.0], [0, 7],
    ):
        grids.append((f"london_{mode}", LondonBreakoutConfig(
            asian_start=as_, asian_end=ae, trade_start=ts_, trade_end=te,
            tp_range_mult=mult, mode=mode, broker_utc_offset_hours=off, equity_sample_bars=96,
        ), run_london_breakout))

    print(f"Screen {len(grids)} configs (full period)\n", flush=True)

    for i, (name, cfg, fn) in enumerate(grids, 1):
        off = getattr(cfg, "broker_utc_offset_hours", 7)
        r = fn(bars, cfg)
        if r.metrics["n_trades"] < 8:
            continue
        ev = evaluate_ws_classic(r, ws_cfg(off))
        row = {
            "strategy": name,
            **cfg.to_dict(),
            "full_pass": ev["checks"]["pass_all"],
            "full_pnl": round(r.total_pnl, 2),
            "full_dd": round(ev["static_dd_pct"], 2),
            "full_trades": r.metrics["n_trades"],
            "full_pf": round(min(r.metrics.get("profit_factor") or 0, 999), 2),
        }
        if ev["checks"]["pass_all"] or (ev["checks"]["pass_static_dd"] and r.total_pnl > 0):
            candidates.append(row)
        if ev["checks"]["pass_all"]:
            print(f"  FULL PASS [{name}] ${row['full_pnl']} trades={row['full_trades']}", flush=True)
        if i % 100 == 0:
            print(f"  {i}/{len(grids)} candidates={len(candidates)}", flush=True)

    candidates.sort(key=lambda x: (x["full_pass"], x["full_pnl"]), reverse=True)
    print(f"\nCandidatos: {len(candidates)} — validando 30d en top {min(40, len(candidates))}\n", flush=True)

    final: list[dict] = []
    for row in candidates[:40]:
        name = row["strategy"]
        off = row.get("broker_utc_offset_hours", 7)
        # rebuild cfg from row
        if name == "ict_judas":
            cfg = JudasConfig(**{k: row[k] for k in JudasConfig.__dataclass_fields__ if k in row})
            fn = run_judas_swing
        elif name == "liq_sweep":
            cfg = LiquiditySweepConfig(**{k: row[k] for k in LiquiditySweepConfig.__dataclass_fields__ if k in row})
            fn = run_liquidity_sweep
        else:
            cfg = LondonBreakoutConfig(**{k: row[k] for k in LondonBreakoutConfig.__dataclass_fields__ if k in row})
            fn = run_london_breakout
        wcfg = ws_cfg(off)
        w30 = simulate_eval_windows(bars, wcfg, window_days=30, step="MS", end="2021-09-01")
        # simulate_eval_windows uses run_fondeo_backtest — need manual
        from webapp.backend.engine.ws_eval import evaluate_ws_classic as ev_fn
        starts = pd.date_range("2017-01-03", "2021-09-01", freq="MS", tz="UTC")
        passed = total = 0
        days_list: list[int] = []
        for s in starts:
            e = s + pd.Timedelta(days=30)
            chunk = bars[(bars["timestamp"] >= s) & (bars["timestamp"] < e)]
            if len(chunk) < 400:
                continue
            total += 1
            rr = fn(chunk, cfg)
            ev = ev_fn(rr, wcfg)
            if ev["checks"]["pass_all"]:
                passed += 1
                if ev["days_to_meta"] is not None:
                    days_list.append(ev["days_to_meta"])
        med = sorted(days_list)[len(days_list) // 2] if days_list else None
        rate = round(100 * passed / total, 1) if total else 0
        enriched = {**row, "w30_pass": passed, "w30_total": total, "w30_rate": rate, "w30_med": med}
        if passed > 0:
            final.append(enriched)
            print(f"  30d HIT [{name}] {rate}% med={med}d full=${row['full_pnl']}", flush=True)

    final.sort(key=lambda x: (x["w30_rate"], x["w30_pass"]), reverse=True)
    OUT.write_text(json.dumps({"candidates": len(candidates), "survivors_30d": len(final), "top": final[:20], "best_full": candidates[:15]}, indent=2), encoding="utf-8")
    print(f"\nSurvivors 30d: {len(final)} → {OUT}", flush=True)


if __name__ == "__main__":
    main()
