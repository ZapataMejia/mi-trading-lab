#!/usr/bin/env python3
"""Reporte de entrega — Liquidity Sweep SAFE (ejecutar el día de la demo)."""
from __future__ import annotations

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

CFG = LiquiditySweepConfig(
    lookback_bars=36,
    sess_start=700,
    sess_end=1400,
    risk_pct=1.5,
    tp_ratio=1.5,
    sl_buffer_pips=3.0,
    max_trades_per_day=1,
    broker_utc_offset_hours=7,
    mm_risk_pct=1.5,
    initial_balance=5000,
    equity_sample_bars=12,
)
WS = FondeoConfig(
    risk_pct=1.5,
    max_trades_per_day=1,
    initial_balance=5000,
    broker_utc_offset_hours=7,
    equity_sample_bars=12,
)

PERIODS = [
    ("validacion_principal", "2022-01-01", "2024-10-30"),
    ("forward_q1_2026", "2026-01-01", "2026-03-31"),
]


def main() -> None:
    df = _normalize_ohlc(pd.read_csv(ROOT / "data/forex_cache/EURUSD_M5.csv"))
    report = {
        "estrategia": "Liquidity Sweep SAFE",
        "cuenta_objetivo": "WS CLASSIC $5k Fase 1",
        "config_file": "data/forex_cache/liq_sweep_safe_config.json",
        "config": CFG.to_dict(),
        "periods": {},
    }

    for name, start, end in PERIODS:
        chunk = df[(df["timestamp"] >= start) & (df["timestamp"] <= end + " 23:59:59")].reset_index(drop=True)
        r = run_liquidity_sweep(chunk, CFG)
        ev = evaluate_ws_classic(r, WS)
        wins = sum(1 for t in r.trades if t.is_winner)
        report["periods"][name] = {
            "start": start,
            "end": end,
            "trades": len(r.trades),
            "win_rate_pct": round(100 * wins / len(r.trades), 1) if r.trades else 0,
            "pnl_usd": round(r.total_pnl, 2),
            "profit_factor": round(r.metrics.get("profit_factor", 0) or 0, 2),
            "pasa_eval_ws": ev["checks"]["pass_all"],
            "dd_estatico_pct": round(ev["static_dd_pct"], 2),
            "dd_diario_max_pct": round(ev["max_daily_loss_pct"], 2),
            "dias_a_meta": ev.get("days_to_meta"),
        }

    out = ROOT / "data/forex_cache/ENTREGA_liq_sweep_safe.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=" * 60)
    print("LIQUIDITY SWEEP SAFE — REPORTE ENTREGA")
    print("=" * 60)
    for name, p in report["periods"].items():
        print(f"\n[{name}] {p['start']} → {p['end']}")
        print(f"  Trades: {p['trades']}  |  PnL: ${p['pnl_usd']:,.2f}  |  PF: {p['profit_factor']}")
        print(f"  Pasa eval WS: {'SÍ' if p['pasa_eval_ws'] else 'NO'}")
        print(f"  DD estático: {p['dd_estatico_pct']}%  |  DD diario max: {p['dd_diario_max_pct']}%")
        print(f"  Días a meta (+8%): {p['dias_a_meta']}")
    print(f"\nJSON guardado: {out}")
    print("\nDemo web: http://localhost:3000/fondeo/liquidity-sweep")
    print("=" * 60)


if __name__ == "__main__":
    main()
