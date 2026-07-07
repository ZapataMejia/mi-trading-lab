"""Barrido de robustez del Agotamiento con el motor REALISTA (5m).

Recorre una rejilla de parámetros (TP, nº de retrocesos, dirección, filtros v2) y
reporta una tabla ordenada por Profit Factor. Objetivo: confirmar si EXISTE alguna
región con ventaja real, o si todo el espacio de parámetros es break-even/perdedor.
"""
from __future__ import annotations

import itertools
import scripts.agotamiento_backtest as agb

# cache de carga para no releer parquet en cada combo
_cache = {}
_orig_load = agb.load


def _cached_load(p):
    key = (p.symbol, p.tf)
    if key not in _cache:
        _cache[key] = _orig_load(p)
    return _cache[key].copy()


agb.load = _cached_load
agb._plot = lambda *a, **k: None  # sin gráficos


def main():
    tps = [1.5, 2.0, 3.0, 4.0, 5.0]
    retraces = [2, 3]
    dirs = ["long", "both"]
    filt_modes = ["pure", "v2"]  # pure = sin filtros; v2 = breakeven1 + max3 + stop-1ª-pérdida
    swing = 2
    symbol = "NQDK"

    rows = []
    for tp, rt, direction, fm in itertools.product(tps, retraces, dirs, filt_modes):
        kw = dict(symbol=symbol, tf="5m", swing=swing, min_retrace_candles=rt,
                  tp_ratio=tp, direction=direction, session=True,
                  realistic_entry_bar=True)  # REALISTA siempre
        if fm == "v2":
            kw.update(breakeven_after_r=1.0, max_trades_per_day=3,
                      stop_after_first_loss=True)
        p = agb.Params(**kw)
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            res = agb.run(p)
        if res.get("n_trades", 0) == 0:
            continue
        rows.append({
            "dir": direction, "tp": tp, "retr": rt, "filt": fm,
            "trades": res["n_trades"], "win": res["win_rate"],
            "pf": res["profit_factor"], "net": res["net_pnl_usd"],
            "dd": res["max_drawdown_usd"],
        })

    rows.sort(key=lambda r: r["pf"], reverse=True)
    print("=" * 86)
    print(f"BARRIDO REALISTA  {symbol} 5m  swing={swing}  (con costos MNQ)  — {len(rows)} combos")
    print("=" * 86)
    print(f"{'dir':5} {'tp':>4} {'retr':>4} {'filt':>5} {'trades':>7} {'win%':>6} {'PF':>6} {'net$':>10} {'maxDD$':>10}")
    print("-" * 86)
    for r in rows:
        flag = "  <== EDGE?" if r["pf"] >= 1.15 else ""
        print(f"{r['dir']:5} {r['tp']:>4} {r['retr']:>4} {r['filt']:>5} {r['trades']:>7} "
              f"{r['win']:>6} {r['pf']:>6} {r['net']:>10} {r['dd']:>10}{flag}")
    print("-" * 86)
    best = rows[0]
    print(f"MEJOR: dir={best['dir']} tp={best['tp']} retr={best['retr']} filt={best['filt']} "
          f"-> PF={best['pf']}  net=${best['net']}")
    n_edge = sum(1 for r in rows if r["pf"] >= 1.15)
    print(f"Combos con PF>=1.15: {n_edge} de {len(rows)}")
    print("=" * 86)


if __name__ == "__main__":
    main()
