#!/usr/bin/env python3
"""Descarga EURUSD M5 mes a mes (Dukascopy vía duka) + merge + research. Resumible."""
from __future__ import annotations

import json
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duka.core.fetch as duka_fetch
import pandas as pd
from duka.app import app as duka_app
from duka.core.utils import TimeFrame

duka_fetch.URL = "https://datafeed.dukascopy.com/datafeed/{currency}/{year}/{month:02d}/{day:02d}/{hour:02d}h_ticks.bi5"

TMP = ROOT / "data/forex_cache/duka_chunks"
OUT = ROOT / "data/forex_cache/EURUSD_M5.csv"
LOG = ROOT / "data/forex_cache/_download.log"
RESUMEN = ROOT / "data/forex_cache/RESUMEN.txt"


def log(msg: str) -> None:
    line = f"{msg}\n"
    print(msg, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line)


def month_range(start_y: int, start_m: int, end_y: int, end_m: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    y, m = start_y, start_m
    while (y, m) <= (end_y, end_m):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def download_month(y: int, m: int) -> bool:
    tag = TMP / f"EURUSD_{y:04d}{m:02d}.csv"
    if tag.exists() and tag.stat().st_size > 1000:
        log(f"skip {tag.name}")
        return True
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) - timedelta(days=1) if m == 12 else date(y, m + 1, 1) - timedelta(days=1)
    log(f"download {y}-{m:02d} ({start} -> {end})...")
    try:
        duka_app(["EURUSD"], start, end, 1, TimeFrame.M5, str(TMP), True)
        produced = sorted(TMP.glob("EURUSD-*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not produced:
            log(f"FAIL {y}-{m:02d}: sin archivo")
            return False
        df = pd.read_csv(produced[0])
        df.to_csv(tag, index=False)
        for p in TMP.glob("EURUSD-*.csv"):
            p.unlink(missing_ok=True)
        log(f"OK {tag.name}: {len(df):,} rows")
        return True
    except Exception as exc:
        log(f"ERROR {y}-{m:02d}: {exc}")
        traceback.print_exc()
        return False


def merge() -> pd.DataFrame:
    frames = []
    for p in sorted(TMP.glob("EURUSD_*.csv")):
        df = pd.read_csv(p)
        if "time" in df.columns:
            df = df.rename(columns={"time": "timestamp"})
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df["volume"] = 0.0
        frames.append(df[["timestamp", "open", "high", "low", "close", "volume"]])
    if not frames:
        raise RuntimeError("Sin chunks")
    return pd.concat(frames, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")


def run_research() -> dict:
    from scripts.fondeo_research import EVAL  # noqa — use inline to capture output
    import itertools
    from webapp.backend.engine.fondeo_engine import FondeoConfig, run_fondeo_backtest

    bars = pd.read_csv(OUT)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)

    base = FondeoConfig()
    rb = run_fondeo_backtest(bars, base)
    m = rb.metrics

    grid = {
        "fast_period": [7, 9, 12],
        "slow_period": [18, 20, 26, 30],
        "risk_pct": [1.0, 1.5, 2.1],
        "tp_ratio": [0.8, 1.0, 1.5],
        "sess_start": [700, 800],
        "sess_end": [900, 1000, 1100],
        "max_trades_per_day": [1, 2],
        "broker_utc_offset_hours": [0, 2],
    }
    keys = list(grid.keys())
    results = []
    for combo in itertools.product(*grid.values()):
        params = dict(zip(keys, combo))
        if params["slow_period"] <= params["fast_period"]:
            continue
        cfg = FondeoConfig(
            **{k: params[k] for k in params if k != "broker_utc_offset_hours"},
            mm_risk_pct=params["risk_pct"],
            broker_utc_offset_hours=params["broker_utc_offset_hours"],
        )
        r = run_fondeo_backtest(bars, cfg)
        if r.metrics["n_trades"] < 10:
            continue
        meta_usd = EVAL["capital"] * EVAL["meta_pct"] / 100
        pass_dd = r.metrics["max_drawdown_pct"] > -EVAL["max_dd_pct"]
        pass_meta = r.total_pnl >= meta_usd
        pass_pf = r.metrics["profit_factor"] >= 1.0
        results.append({
            **params,
            "trades": r.metrics["n_trades"],
            "wr": round(r.metrics["win_rate_pct"], 1),
            "pnl": round(r.total_pnl, 2),
            "pnl_pct": round(r.total_pnl_pct, 2),
            "dd": round(r.metrics["max_drawdown_pct"], 2),
            "pf": round(r.metrics["profit_factor"], 2),
            "pass_dd": pass_dd,
            "pass_meta": pass_meta,
            "pass_pf": pass_pf,
            "pass_all": pass_dd and pass_meta and pass_pf,
        })

    results.sort(key=lambda x: (x["pass_all"], x["pass_dd"], x["pnl"]), reverse=True)
    return {
        "bars": len(bars),
        "from": str(bars["timestamp"].iloc[0]),
        "to": str(bars["timestamp"].iloc[-1]),
        "baseline": {
            "trades": m["n_trades"],
            "pnl": round(rb.total_pnl, 2),
            "dd": round(m["max_drawdown_pct"], 2),
            "pf": round(m["profit_factor"], 2),
        },
        "top10": results[:10],
        "pass_all_count": sum(1 for x in results if x["pass_all"]),
        "total_configs": len(results),
    }


def write_resumen(data: dict, chunks: int) -> None:
    lines = [
        "=== FONdeo EMA — resumen automático ===",
        f"Chunks descargados: {chunks}/63",
        f"CSV: {len(pd.read_csv(OUT)):,} barras" if OUT.exists() else "CSV: pendiente",
        f"Rango: {data.get('from', '?')} -> {data.get('to', '?')}",
        "",
        "BASELINE (9/20, 2.1%, sess 8-10):",
        f"  {data['baseline']}",
        "",
        f"Configs evaluadas (>=10 trades): {data.get('total_configs', 0)}",
        f"Pasaron DD+meta+PF: {data.get('pass_all_count', 0)}",
        "",
        "TOP 3 para validar en SQX:",
    ]
    for i, x in enumerate(data.get("top10", [])[:3], 1):
        flags = []
        if x.get("pass_all"):
            flags.append("EVAL OK")
        elif x.get("pass_dd"):
            flags.append("DD ok")
        lines.append(
            f"  {i}. EMA {x['fast_period']}/{x['slow_period']} risk={x['risk_pct']}% TP={x['tp_ratio']} "
            f"sess {x['sess_start']}-{x['sess_end']} off={x['broker_utc_offset_hours']} max/d={x['max_trades_per_day']}"
        )
        lines.append(
            f"     {x['trades']}t PnL=${x['pnl']} DD={x['dd']}% PF={x['pf']} {' '.join(flags)}"
        )
    lines += [
        "",
        "Próximo paso al volver: export CSV desde VPS SQX y validar top config en AlgoWizard.",
        "Lab: http://localhost:3000/fondeo",
    ]
    RESUMEN.write_text("\n".join(lines), encoding="utf-8")
    (ROOT / "data/forex_cache/research_results.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    months = month_range(2017, 1, 2022, 3)
    log("=== INICIO download_all_dukascopy ===")
    ok = 0
    for y, m in months:
        if download_month(y, m):
            ok += 1

    log(f"merge ({ok}/{len(months)} meses)...")
    out = merge()
    out.to_csv(OUT, index=False)
    log(f"CSV {OUT}: {len(out):,} barras | {out['timestamp'].iloc[0]} -> {out['timestamp'].iloc[-1]}")

    log("research...")
    data = run_research()
    write_resumen(data, ok)
    log("=== FIN ===")


if __name__ == "__main__":
    main()
