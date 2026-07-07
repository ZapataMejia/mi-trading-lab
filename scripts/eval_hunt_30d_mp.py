#!/usr/bin/env python3
"""Hunt 30d con multiprocessing — hold overnight + sesión amplia."""
from __future__ import annotations

import itertools
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import pandas as pd

from eval_hunt_no_sess_close import run_no_sess_close  # noqa: E402
from webapp.backend.engine.fondeo_engine import FondeoConfig, run_fondeo_backtest
from webapp.backend.engine.ws_eval import evaluate_ws_classic
from webapp.backend.markets.forex import _normalize_ohlc

CSV = ROOT / "data/forex_cache/EURUSD_M5.csv"
OUT = ROOT / "data/forex_cache/hunt_30d_mp.json"

WINDOW_START = "2017-01-03"
WINDOW_END = "2021-09-01"
WINDOW_DAYS = 30


def _grid() -> list[dict]:
    emas = [
        (2, 5), (2, 8), (3, 6), (3, 8), (3, 10), (4, 9), (4, 12),
        (5, 11), (5, 15), (6, 14), (8, 18), (9, 18), (9, 20), (9, 21),
    ]
    sessions = [
        (600, 1200), (600, 1400), (600, 1600),
        (700, 1100), (700, 1400), (700, 1600),
        (800, 1000), (800, 1200), (800, 1400), (800, 1600),
        (900, 1200), (900, 1500),
    ]
    offsets = [0, 7]
    tps = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
    modes = ["hold", "session"]
    dirs = ["both", "long", "short"]
    out = []
    for (f, s), (ss, se), off, tp, mode, d in itertools.product(
        emas, sessions, offsets, tps, modes, dirs
    ):
        allow_long = d in ("both", "long")
        allow_short = d in ("both", "short")
        out.append({
            "fast_period": f, "slow_period": s, "risk_pct": 2.1, "tp_ratio": tp,
            "sess_start": ss, "sess_end": se, "max_trades_per_day": 2,
            "broker_utc_offset_hours": off, "mode": mode, "direction": d,
            "allow_long": allow_long, "allow_short": allow_short,
        })
    return out


def _eval_windows(bars: pd.DataFrame, cfg: FondeoConfig, run_fn) -> dict:
    starts = pd.date_range(WINDOW_START, WINDOW_END, freq="MS", tz="UTC")
    passed = total = 0
    days_list: list[int] = []
    for s in starts:
        e = s + pd.Timedelta(days=WINDOW_DAYS)
        chunk = bars[(bars["timestamp"] >= s) & (bars["timestamp"] < e)]
        if len(chunk) < 400:
            continue
        total += 1
        r = run_fn(chunk, cfg)
        ev = evaluate_ws_classic(r, cfg)
        if ev["checks"]["pass_all"]:
            passed += 1
            if ev["days_to_meta"] is not None:
                days_list.append(ev["days_to_meta"])
    med = sorted(days_list)[len(days_list) // 2] if days_list else None
    rate = round(100 * passed / total, 1) if total else 0.0
    return {"w30_rate": rate, "w30_pass": passed, "w30_attempts": total, "w30_med": med}


_BARS: pd.DataFrame | None = None


def _init_worker(bars_path: str) -> None:
    global _BARS
    df = _normalize_ohlc(pd.read_csv(bars_path))
    _BARS = df[(df["timestamp"] >= "2017-01-03") & (df["timestamp"] <= "2022-03-31")].reset_index(drop=True)


def _test_one(params: dict) -> dict | None:
    assert _BARS is not None
    mode = params.pop("mode")
    direction = params.pop("direction")
    p = {k: v for k, v in params.items() if k not in ("allow_long", "allow_short")}
    cfg = FondeoConfig(
        **p,
        mm_risk_pct=2.1,
        equity_sample_bars=48,
        allow_long=params["allow_long"],
        allow_short=params["allow_short"],
    )
    run_fn = run_no_sess_close if mode == "hold" else run_fondeo_backtest
    m = _eval_windows(_BARS, cfg, run_fn)
    if m["w30_pass"] == 0:
        return None
    r = run_fn(_BARS, cfg)
    ev = evaluate_ws_classic(r, cfg)
    return {
        **params, "mode": mode, "direction": direction,
        **m,
        "full_pass": ev["checks"]["pass_all"],
        "full_pnl": round(r.total_pnl, 2),
        "full_trades": r.metrics["n_trades"],
        "full_dd": round(ev["static_dd_pct"], 2),
    }


def main() -> None:
    g = _grid()
    print(f"HUNT 30d MP — {len(g)} combos, {WINDOW_DAYS}d windows\n", flush=True)

    hits: list[dict] = []
    done = 0
    workers = min(8, os.cpu_count() or 4)
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker, initargs=(str(CSV),)) as ex:
        futs = {ex.submit(_test_one, dict(p)): p for p in g}
        for fut in as_completed(futs):
            done += 1
            if done % 200 == 0:
                print(f"  {done}/{len(g)} survivors={len(hits)}", flush=True)
            try:
                res = fut.result()
                if res:
                    hits.append(res)
                    print(
                        f"  HIT {res['mode']} EMA {res['fast_period']}/{res['slow_period']} "
                        f"TP{res['tp_ratio']} {res['sess_start']}-{res['sess_end']} {res['direction']} "
                        f"| {res['w30_rate']}% med={res['w30_med']}d",
                        flush=True,
                    )
            except Exception as e:
                print(f"  ERR: {e}", flush=True)

    hits.sort(key=lambda x: (x["w30_rate"], x["w30_pass"], x.get("full_pnl", 0)), reverse=True)

    print(f"\n=== TOTAL SURVIVORS: {len(hits)} ===", flush=True)
    for x in hits[:12]:
        print(
            f"  [{x['mode']}] EMA {x['fast_period']}/{x['slow_period']} TP{x['tp_ratio']} "
            f"{x['sess_start']}-{x['sess_end']} off{x['broker_utc_offset_hours']} {x['direction']} "
            f"| 30d {x['w30_rate']}% ({x['w30_pass']}/{x['w30_attempts']}) med={x['w30_med']}d "
            f"full=${x['full_pnl']}",
            flush=True,
        )

    OUT.write_text(json.dumps({"survivors": len(hits), "top": hits[:30]}, indent=2), encoding="utf-8")
    print(f"\n→ {OUT}", flush=True)


if __name__ == "__main__":
    main()
