#!/usr/bin/env python3
"""Hunt 30d 2 fases: screening trimestral → validación mensual."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import pandas as pd

from eval_hunt_no_sess_close import run_no_sess_close
from webapp.backend.engine.fondeo_engine import FondeoConfig, run_fondeo_backtest
from webapp.backend.engine.ws_eval import evaluate_ws_classic
from webapp.backend.markets.forex import _normalize_ohlc

CSV = ROOT / "data/forex_cache/EURUSD_M5.csv"
OUT = ROOT / "data/forex_cache/hunt_30d_phase.json"


def load_bars() -> pd.DataFrame:
    df = _normalize_ohlc(pd.read_csv(CSV))
    return df[(df["timestamp"] >= "2017-01-03") & (df["timestamp"] <= "2022-03-31")].reset_index(drop=True)


def grid_phase1() -> list[dict]:
    emas = [(2, 5), (2, 8), (3, 6), (3, 8), (3, 10), (4, 9), (5, 11), (6, 14), (8, 18), (9, 18), (9, 20)]
    sessions = [(600, 1600), (700, 1400), (700, 1600), (800, 1200), (800, 1600), (900, 1500)]
    tps = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
    out = []
    for (f, s), (ss, se), tp in itertools.product(emas, sessions, tps):
        for off in (0, 7):
            for mode in ("hold", "session"):
                out.append({
                    "fast_period": f, "slow_period": s, "risk_pct": 2.1, "tp_ratio": tp,
                    "sess_start": ss, "sess_end": se, "max_trades_per_day": 2,
                    "broker_utc_offset_hours": off, "mode": mode,
                })
    return out


def eval_windows(bars, cfg, run_fn, freq: str) -> dict:
    starts = pd.date_range("2017-01-03", "2021-09-01", freq=freq, tz="UTC")
    passed = total = 0
    days_list: list[int] = []
    meta_only = 0
    for s in starts:
        e = s + pd.Timedelta(days=30)
        chunk = bars[(bars["timestamp"] >= s) & (bars["timestamp"] < e)]
        if len(chunk) < 400:
            continue
        total += 1
        r = run_fn(chunk, cfg)
        ev = evaluate_ws_classic(r, cfg)
        if r.total_pnl >= 400:
            meta_only += 1
        if ev["checks"]["pass_all"]:
            passed += 1
            if ev["days_to_meta"] is not None:
                days_list.append(ev["days_to_meta"])
    med = sorted(days_list)[len(days_list) // 2] if days_list else None
    rate = round(100 * passed / total, 1) if total else 0.0
    meta_rate = round(100 * meta_only / total, 1) if total else 0.0
    return {"pass": passed, "total": total, "rate": rate, "med": med, "meta_rate": meta_rate}


def main() -> None:
    bars = load_bars()
    g = grid_phase1()
    print(f"FASE 1 — {len(g)} configs, ventanas trimestrales (QS)\n", flush=True)

    phase1_hits: list[dict] = []
    for i, p in enumerate(g, 1):
        if i % 100 == 0:
            print(f"  {i}/{len(g)} hits={len(phase1_hits)}", flush=True)
        mode = p.pop("mode")
        cfg = FondeoConfig(**p, mm_risk_pct=2.1, equity_sample_bars=96)
        run_fn = run_no_sess_close if mode == "hold" else run_fondeo_backtest
        m = eval_windows(bars, cfg, run_fn, "QS")
        p["mode"] = mode
        if m["pass"] > 0 or m["meta_rate"] >= 25:
            phase1_hits.append({**p, **m, "phase1": True})

    phase1_hits.sort(key=lambda x: (x["rate"], x["meta_rate"], x["pass"]), reverse=True)
    print(f"\nFase 1: {len(phase1_hits)} candidatos (pass>0 o meta≥25% trimestral)\n", flush=True)

    # Fase 2: validación mensual en top candidatos + todos con pass>0
    candidates = [x for x in phase1_hits if x["pass"] > 0]
    if not candidates:
        candidates = phase1_hits[:40]
    print(f"FASE 2 — {len(candidates)} configs, ventanas mensuales (MS)\n", flush=True)

    final: list[dict] = []
    for p in candidates:
        mode = p["mode"]
        params = {k: p[k] for k in (
            "fast_period", "slow_period", "risk_pct", "tp_ratio", "sess_start",
            "sess_end", "max_trades_per_day", "broker_utc_offset_hours",
        )}
        cfg = FondeoConfig(**params, mm_risk_pct=2.1, equity_sample_bars=48)
        run_fn = run_no_sess_close if mode == "hold" else run_fondeo_backtest
        m = eval_windows(bars, cfg, run_fn, "MS")
        r = run_fn(bars, cfg)
        ev = evaluate_ws_classic(r, cfg)
        row = {**params, "mode": mode, "w30_pass": m["pass"], "w30_total": m["total"],
               "w30_rate": m["rate"], "w30_med": m["med"], "meta_rate_30d": m["meta_rate"],
               "full_pass": ev["checks"]["pass_all"], "full_pnl": round(r.total_pnl, 2),
               "full_dd": round(ev["static_dd_pct"], 2), "full_trades": r.metrics["n_trades"]}
        if m["pass"] > 0:
            final.append(row)
            print(
                f"  PASS [{mode}] EMA {row['fast_period']}/{row['slow_period']} TP{row['tp_ratio']} "
                f"{row['sess_start']}-{row['sess_end']} | {row['w30_rate']}% med={row['w30_med']}d",
                flush=True,
            )

    final.sort(key=lambda x: (x["w30_rate"], x["w30_pass"]), reverse=True)
    print(f"\n=== FINAL: {len(final)} configs pasan eval 30d ===", flush=True)
    for x in final[:10]:
        print(
            f"  [{x['mode']}] EMA {x['fast_period']}/{x['slow_period']} TP{x['tp_ratio']} "
            f"{x['sess_start']}-{x['sess_end']} off{x['broker_utc_offset_hours']} "
            f"| {x['w30_rate']}% ({x['w30_pass']}/{x['w30_total']}) med={x['w30_med']}d full=${x['full_pnl']}",
            flush=True,
        )

    OUT.write_text(json.dumps({"phase1_candidates": len(phase1_hits), "final_survivors": len(final), "top": final[:20], "phase1_top": phase1_hits[:20]}, indent=2), encoding="utf-8")
    print(f"\n→ {OUT}", flush=True)


if __name__ == "__main__":
    main()
