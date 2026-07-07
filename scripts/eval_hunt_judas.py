#!/usr/bin/env python3
"""Hunt ICT Judas — la alternativa más prometedora vs EMA."""
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
from webapp.backend.engine.ws_eval import evaluate_ws_classic
from webapp.backend.markets.forex import _normalize_ohlc

CSV = ROOT / "data/forex_cache/EURUSD_M5.csv"
OUT = ROOT / "data/forex_cache/hunt_judas.json"


def main() -> None:
    df = _normalize_ohlc(pd.read_csv(CSV))
    bars = df[(df["timestamp"] >= "2017-01-03") & (df["timestamp"] <= "2022-03-31")].reset_index(drop=True)
    wcfg = FondeoConfig(broker_utc_offset_hours=7, equity_sample_bars=96)

    grid = list(itertools.product(
        [(0, 600), (0, 700), (100, 700), (200, 700)],
        [(700, 900), (700, 1000), (700, 1100), (800, 1000), (800, 1100)],
        ["asian_opposite", "range_mult"],
        [1.5, 2.0, 2.5, 3.0],
        [8.0, 10.0, 12.0, 15.0, 20.0],
        [1, 2],
        [0, 7],
    ))
    print(f"Judas hunt: {len(grid)} combos\n", flush=True)

    results: list[dict] = []
    for i, ((as_, ae), (ks, ke), tp_mode, tp_mult, min_rng, max_td, off) in enumerate(grid, 1):
        cfg = JudasConfig(
            asian_start=as_, asian_end=ae, kill_start=ks, kill_end=ke,
            tp_mode=tp_mode, tp_range_mult=tp_mult, min_asian_range_pips=min_rng,
            max_trades_per_day=max_td, broker_utc_offset_hours=off, equity_sample_bars=96,
        )
        r = run_judas_swing(bars, cfg)
        if r.metrics["n_trades"] < 15:
            continue
        ev = evaluate_ws_classic(r, FondeoConfig(broker_utc_offset_hours=off, equity_sample_bars=96))
        row = {
            **cfg.to_dict(),
            "full_pass": ev["checks"]["pass_all"],
            "full_pnl": round(r.total_pnl, 2),
            "full_dd": round(ev["static_dd_pct"], 2),
            "full_trades": r.metrics["n_trades"],
            "full_pf": round(min(r.metrics.get("profit_factor") or 0, 999), 2),
            "pass_meta": ev["checks"]["pass_meta"],
            "pass_dd": ev["checks"]["pass_static_dd"],
        }
        results.append(row)
        if ev["checks"]["pass_all"]:
            print(f"  FULL PASS kill {ks}-{ke} {tp_mode} min{min_rng} max{max_td}/d | ${row['full_pnl']}", flush=True)
        elif ev["checks"]["pass_static_dd"] and r.total_pnl > 200:
            print(f"  NEAR kill {ks}-{ke} pnl=${row['full_pnl']} dd={row['full_dd']}%", flush=True)
        if i % 80 == 0:
            print(f"  {i}/{len(grid)}", flush=True)

    results.sort(key=lambda x: (x["full_pass"], x["pass_dd"], x["full_pnl"]), reverse=True)

    # 30d validation top 25
    top = [x for x in results if x["full_pass"]][:25]
    if not top:
        top = sorted([x for x in results if x["pass_dd"]], key=lambda x: x["full_pnl"], reverse=True)[:25]

    final_30d: list[dict] = []
    starts = pd.date_range("2017-01-03", "2021-09-01", freq="MS", tz="UTC")
    for row in top:
        cfg = JudasConfig(**{k: row[k] for k in JudasConfig.__dataclass_fields__ if k in row})
        off = row["broker_utc_offset_hours"]
        passed = total = 0
        days_list: list[int] = []
        for s in starts:
            e = s + pd.Timedelta(days=30)
            chunk = bars[(bars["timestamp"] >= s) & (bars["timestamp"] < e)]
            if len(chunk) < 400:
                continue
            total += 1
            rr = run_judas_swing(chunk, cfg)
            ev = evaluate_ws_classic(rr, FondeoConfig(broker_utc_offset_hours=off, equity_sample_bars=96))
            if ev["checks"]["pass_all"]:
                passed += 1
                if ev["days_to_meta"] is not None:
                    days_list.append(ev["days_to_meta"])
        med = sorted(days_list)[len(days_list) // 2] if days_list else None
        rate = round(100 * passed / total, 1) if total else 0
        enriched = {**row, "w30_pass": passed, "w30_total": total, "w30_rate": rate, "w30_med": med}
        if passed > 0:
            final_30d.append(enriched)
            print(f"  30d HIT {rate}% med={med}d kill {row['kill_start']}-{row['kill_end']}", flush=True)

    OUT.write_text(json.dumps({
        "survivors_full": sum(1 for x in results if x["full_pass"]),
        "survivors_30d": len(final_30d),
        "top_full": [x for x in results if x["full_pass"]][:15],
        "top_near": sorted([x for x in results if x["pass_dd"] and not x["full_pass"]], key=lambda x: x["full_pnl"], reverse=True)[:10],
        "top_30d": final_30d[:15],
    }, indent=2), encoding="utf-8")
    print(f"\nFull pass: {sum(1 for x in results if x['full_pass'])} | 30d: {len(final_30d)} → {OUT}", flush=True)


if __name__ == "__main__":
    main()
