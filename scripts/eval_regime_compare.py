#!/usr/bin/env python3
"""Compara Liquidity Sweep SAFE vs variantes filtro ADX/ATR — mes 2026 + OOS w30."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from webapp.backend.engine.fondeo_engine import FondeoConfig
from webapp.backend.engine.liquidity_sweep_engine import LiquiditySweepConfig, run_liquidity_sweep
from webapp.backend.engine.ws_eval import evaluate_ws_classic
from webapp.backend.markets.forex import _normalize_ohlc

OUT = ROOT / "data/forex_cache/liq_sweep_regime_compare.json"
OUT_BEST = ROOT / "data/forex_cache/liq_sweep_regime_best.json"

SAFE_BASE = dict(
    lookback_bars=36, sess_start=700, sess_end=1400, risk_pct=1.5, tp_ratio=1.5,
    sl_buffer_pips=3.0, max_trades_per_day=1, broker_utc_offset_hours=7,
    mm_risk_pct=1.5, equity_sample_bars=12, equal_tolerance_pips=3.0,
)

WS = FondeoConfig(risk_pct=1.5, max_trades_per_day=1, initial_balance=5000,
                  broker_utc_offset_hours=7, equity_sample_bars=12)


def cfg(**overrides) -> LiquiditySweepConfig:
    d = {**SAFE_BASE, **overrides}
    return LiquiditySweepConfig(**d)


def month_rows(bars: pd.DataFrame, c: LiquiditySweepConfig, year: int, month_from: int, month_to: int) -> list[dict]:
    names = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    rows = []
    for m in range(month_from, month_to + 1):
        chunk = bars[(bars.timestamp.dt.year == year) & (bars.timestamp.dt.month == m)].reset_index(drop=True)
        if len(chunk) < 200:
            continue
        r = run_liquidity_sweep(chunk, c)
        ev = evaluate_ws_classic(r, WS)
        rows.append({
            "month": m,
            "label": f"{names[m]} {year}",
            "pnl": round(r.total_pnl, 2),
            "pass": ev["checks"]["pass_all"],
            "dd": ev["static_dd_pct"],
            "trades": r.metrics["n_trades"],
        })
    return rows


def w30_rate(bars: pd.DataFrame, c: LiquiditySweepConfig) -> dict:
    df = bars[(bars.timestamp >= "2022-01-01") & (bars.timestamp <= "2024-10-30")].copy()
    starts = pd.date_range("2022-01-01", "2024-08-01", freq="2MS", tz="UTC")
    passed = total = 0
    for s in starts:
        chunk = df[(df.timestamp >= s) & (df.timestamp < s + pd.Timedelta(days=30))]
        if len(chunk) < 400:
            continue
        total += 1
        if evaluate_ws_classic(run_liquidity_sweep(chunk.reset_index(drop=True), c), WS)["checks"]["pass_all"]:
            passed += 1
    return {"passed": passed, "total": total, "rate_pct": round(100 * passed / total, 1) if total else 0}


def score_variant(months: list[dict], w30: dict, label: str, params: dict) -> dict:
    feb = next((x for x in months if x["month"] == 2), None)
    jun = next((x for x in months if x["month"] == 6), None)
    pass_m = sum(1 for x in months if x["pass"])
    pnl_m = sum(x["pnl"] for x in months)
    # Prioridad: w30 OOS, meses 2026 pass, evitar feb/jun deep loss
    feb_ok = (feb["pnl"] > -100) if feb else True
    jun_ok = (jun["pnl"] > -100) if jun else True
    return {
        "label": label,
        "params": params,
        "w30": w30,
        "months_2026": months,
        "pass_months_2026": pass_m,
        "pnl_2026_h1": round(pnl_m, 2),
        "feb_pnl": feb["pnl"] if feb else None,
        "jun_pnl": jun["pnl"] if jun else None,
        "feb_jun_ok": feb_ok and jun_ok,
    }


def main() -> None:
    df = _normalize_ohlc(pd.read_csv(ROOT / "data/forex_cache/EURUSD_M5.csv"))

    variants: list[tuple[str, LiquiditySweepConfig]] = [("SAFE (sin filtro)", cfg(use_regime_filter=False))]

    grid = []
    for adx_min, adx_max, min_atr, max_atr in itertools.product(
        [0, 18, 20, 22],
        [0, 28, 32, 35],
        [0, 6, 8, 10],
        [0, 25, 35],
    ):
        if adx_min == 0 and adx_max == 0 and min_atr == 0 and max_atr == 0:
            continue
        if adx_min > 0 and adx_max > 0 and adx_min >= adx_max:
            continue
        grid.append((adx_min, adx_max, min_atr, max_atr))

    for adx_min, adx_max, min_atr, max_atr in grid:
        parts = []
        if adx_min:
            parts.append(f"adx≥{adx_min}")
        if adx_max:
            parts.append(f"adx≤{adx_max}")
        if min_atr:
            parts.append(f"atr≥{min_atr}")
        if max_atr:
            parts.append(f"atr≤{max_atr}")
        label = " + ".join(parts) or "filtro"
        variants.append((
            label,
            cfg(
                use_regime_filter=True,
                adx_min=float(adx_min),
                adx_max=float(adx_max),
                min_atr_pips=float(min_atr),
                max_atr_pips=float(max_atr),
            ),
        ))

    print(f"Variantes: {len(variants)}\n", flush=True)
    results = []
    for i, (label, c) in enumerate(variants, 1):
        months = month_rows(df, c, 2026, 1, 6)
        w30 = w30_rate(df, c)
        params = {k: v for k, v in c.to_dict().items() if k in (
            "use_regime_filter", "adx_min", "adx_max", "min_atr_pips", "max_atr_pips", "adx_period", "atr_period")}
        row = score_variant(months, w30, label, params)
        results.append(row)
        if i % 20 == 0 or i == 1:
            print(f"  {i}/{len(variants)} {label[:40]} w30={w30['rate_pct']}% pass6={row['pass_months_2026']}", flush=True)

    baseline = results[0]
    results.sort(key=lambda x: (
        x["w30"]["rate_pct"],
        x["pass_months_2026"],
        x["feb_jun_ok"],
        x["pnl_2026_h1"],
    ), reverse=True)

    best = results[0]
    improved = (
        best["label"] != baseline["label"]
        and (
            best["w30"]["rate_pct"] > baseline["w30"]["rate_pct"]
            or (best["pass_months_2026"] > baseline["pass_months_2026"] and best["w30"]["rate_pct"] >= baseline["w30"]["rate_pct"] - 2)
        )
    )

    payload = {
        "baseline": baseline,
        "best": best,
        "improved": improved,
        "top5": results[:5],
        "variants_tested": len(results),
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if improved:
        OUT_BEST.write_text(json.dumps({"name": "Liquidity Sweep SAFE + régimen", **best}, indent=2), encoding="utf-8")

    print(f"\nBASELINE: w30={baseline['w30']['rate_pct']}% pass_2026={baseline['pass_months_2026']}/6 feb={baseline['feb_pnl']} jun={baseline['jun_pnl']}")
    print(f"MEJOR:    {best['label']}")
    print(f"          w30={best['w30']['rate_pct']}% pass_2026={best['pass_months_2026']}/6 feb={best['feb_pnl']} jun={best['jun_pnl']}")
    print(f"improved={improved}\n→ {OUT}")

    print("\n=== 2026 mes a mes: BASELINE vs MEJOR ===")
    for bm, om in zip(baseline["months_2026"], best["months_2026"]):
        print(f"  {bm['label']}: SAFE ${bm['pnl']:+.0f} {'PASS' if bm['pass'] else 'FAIL'} | {best['label'][:30]} ${om['pnl']:+.0f} {'PASS' if om['pass'] else 'FAIL'}")


if __name__ == "__main__":
    main()
