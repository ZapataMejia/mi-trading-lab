"""Backtester FIEL al video de la estrategia "Agotamientos" (Cristian / TFT).

A diferencia de scripts/agotamiento_backtest.py (versión esquelética en 5m), este
intenta replicar lo que Cris hace en el video, según Estrategia_Agotamiento_Cristian.md:

  - ESTRUCTURA en 5m: módulo de arranque (swing low/high) + impulso que rompe estructura.
    Mientras el sesgo 5m está activo (módulo intacto), se habilita la ejecución en 1m.
  - EJECUCIÓN en 1m: retroceso de >=N velas CONTINUAS (rojas para largo; dojis cuentan
    a favor), línea de agotamiento = máximo con mecha de la última vela roja.
  - ENTRADA por CIERRE DE CUERPO: se entra cuando una vela de 1m CIERRA con el cuerpo
    más allá de la línea (close > línea para largo). Entrada al cierre de esa vela
    (≈ "últimos 10 segundos"), NO una orden stop que se llena en un pinchazo de mecha.
    -> Como se entra al cierre, los SL/TP se evalúan desde la vela SIGUIENTE (fiel).
  - SL: zona de riesgo en 1m (mínimo del retroceso - buffer).  TP: ratio * riesgo.
  - HORARIO: entradas solo hasta el cutoff (13:30 ET por defecto); cierre forzado de
    cualquier posición a las 15:00 ET.
  - DISCIPLINA: máx N entradas/día; si la 1ª del día da SL -> fuera ese día.
  - FILTRO S/R ("ley" de Cris): no entrar si hay una resistencia (largo) / soporte (corto)
    de alta temporalidad pegada (pivotes 1H + máximo/mínimo del día previo).

Lo discrecional del video (manipulación, dirección "clara a ojo", cierres manuales,
escalado con ATM, filtro de noticias) NO se automatiza aquí.

Uso:
  python3 scripts/agotamiento_faithful.py --symbol NQDK --direction long
  python3 scripts/agotamiento_faithful.py --symbol NQDK --direction both --no-sr
"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, asdict
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent.parent / ".mplcache"))

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "raw" / "nasdaq"
OUT = ROOT / "data" / "agotamiento"
OUT.mkdir(parents=True, exist_ok=True)


@dataclass
class Params:
    symbol: str = "NQDK"
    swing5m: int = 2              # velas a cada lado para pivote en 5m (estructura)
    min_run_1m: int = 3           # velas continuas mínimas del retroceso en 1m
    tp_ratio: float = 3.0
    sl_buffer_ticks: float = 1.0
    tick: float = 0.25
    point_value: float = 2.0      # MNQ
    commission_rt: float = 1.24
    slippage_ticks: float = 1.0
    direction: str = "both"
    sess_start: str = "09:30"     # no entrar antes
    entry_cutoff: str = "13:30"   # no entrar después (11:30 Denver = 13:30 ET)
    force_close: str = "15:00"    # cerrar todo (13:00 Denver = 15:00 ET)
    max_trades_per_day: int = 3
    stop_after_first_loss: bool = True
    # --- filtro S/R ---
    use_sr: bool = True
    sr_pivot_1h: int = 3          # velas a cada lado para pivote en 1H
    sr_near_frac: float = 0.0015  # "pegado" = dentro de 0.15% del precio de entrada
    sr_lookback_days: int = 15    # ventana de pivotes 1H vigentes


def load_1m(p: Params) -> pd.DataFrame:
    df = pd.read_parquet(DATA / f"{p.symbol}_1m.parquet")
    df = df[["open", "high", "low", "close", "volume"]].dropna()
    df = df[~df.index.duplicated(keep="first")].sort_index()
    return df


def resample(df1m: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    r = df1m.resample(rule, label="left", closed="left").agg(agg).dropna()
    return r


def confirmed_pivots(high: np.ndarray, low: np.ndarray, L: int):
    """Para cada barra t: precio del último swing high/low YA confirmado (pivote en i
    se confirma en i+L, sin mirar al futuro)."""
    n = len(high)
    sh_at = np.full(n, np.nan)
    sl_at = np.full(n, np.nan)
    for i in range(L, n - L):
        wh = high[i - L:i + L + 1]
        wl = low[i - L:i + L + 1]
        if high[i] == wh.max() and (wh == high[i]).sum() == 1:
            sh_at[i] = high[i]
        if low[i] == wl.min() and (wl == low[i]).sum() == 1:
            sl_at[i] = low[i]
    last_sh = np.full(n, np.nan)
    last_sl = np.full(n, np.nan)
    cur_sh = np.nan
    cur_sl = np.nan
    for t in range(n):
        src = t - L
        if src >= 0:
            if not np.isnan(sh_at[src]):
                cur_sh = sh_at[src]
            if not np.isnan(sl_at[src]):
                cur_sl = sl_at[src]
        last_sh[t] = cur_sh
        last_sl[t] = cur_sl
    return last_sh, last_sl, sh_at, sl_at


def bias_5m(df5: pd.DataFrame, swing: int):
    """Estado de sesgo en 5m: long_active / short_active y su módulo, por barra de 5m."""
    h = df5["high"].values
    lo = df5["low"].values
    c = df5["close"].values
    last_sh, last_sl, _, _ = confirmed_pivots(h, lo, swing)
    n = len(df5)
    long_active = np.zeros(n, dtype=bool)
    short_active = np.zeros(n, dtype=bool)
    module_long = np.full(n, np.nan)
    module_short = np.full(n, np.nan)
    la = False
    sa = False
    ml = np.nan
    ms = np.nan
    for t in range(n):
        # LONG bias
        if not la:
            if not np.isnan(last_sh[t]) and c[t] > last_sh[t] and not np.isnan(last_sl[t]):
                la = True
                ml = last_sl[t]
        else:
            if lo[t] < ml:
                la = False
                ml = np.nan
        # SHORT bias
        if not sa:
            if not np.isnan(last_sl[t]) and c[t] < last_sl[t] and not np.isnan(last_sh[t]):
                sa = True
                ms = last_sh[t]
        else:
            if h[t] > ms:
                sa = False
                ms = np.nan
        long_active[t] = la
        short_active[t] = sa
        module_long[t] = ml
        module_short[t] = ms
    out = pd.DataFrame({
        "long_active": long_active, "short_active": short_active,
        "module_long": module_long, "module_short": module_short,
    }, index=df5.index)
    # disponible recién al CIERRE de la vela 5m -> correr el índice +5min (sin lookahead)
    out.index = out.index + pd.Timedelta(minutes=5)
    return out


def sr_levels_1h(df1m: pd.DataFrame, L: int):
    """Pivotes confirmados en 1H -> (confirm_time, price, kind) ordenados por confirm_time."""
    df1h = resample(df1m, "1h")
    h = df1h["high"].values
    lo = df1h["low"].values
    _, _, sh_at, sl_at = confirmed_pivots(h, lo, L)
    times = df1h.index
    levels = []  # (confirm_time, price, kind)  kind: +1 resistencia, -1 soporte
    for i in range(len(df1h)):
        ct = times[i] + pd.Timedelta(hours=L)  # confirmado L horas después
        if not np.isnan(sh_at[i]):
            levels.append((ct, sh_at[i], 1))
        if not np.isnan(sl_at[i]):
            levels.append((ct, sl_at[i], -1))
    levels.sort(key=lambda x: x[0])
    return levels


def run(p: Params) -> dict:
    df1m = load_1m(p)
    df5 = resample(df1m, "5min")

    bias = bias_5m(df5, p.swing5m)
    bias1m = bias.reindex(df1m.index, method="ffill")

    o = df1m["open"].values
    h = df1m["high"].values
    lo = df1m["low"].values
    c = df1m["close"].values
    idx = df1m.index
    n = len(df1m)

    la1 = bias1m["long_active"].fillna(False).values.astype(bool)
    sa1 = bias1m["short_active"].fillna(False).values.astype(bool)

    # máximo/mínimo del DÍA PREVIO (S/R principal), por fecha
    daily = df1m.resample("1D").agg({"high": "max", "low": "min"}).dropna()
    pdh = daily["high"].shift(1)
    pdl = daily["low"].shift(1)
    dates = idx.normalize()
    pdh_1m = pdh.reindex(dates).values
    pdl_1m = pdl.reindex(dates).values

    # pivotes 1H para S/R
    sr = sr_levels_1h(df1m, p.sr_pivot_1h) if p.use_sr else []
    sr_times = np.array([x[0].value for x in sr]) if sr else np.array([])
    sr_price = np.array([x[1] for x in sr]) if sr else np.array([])
    sr_kind = np.array([x[2] for x in sr]) if sr else np.array([])
    sr_ptr = 0
    sr_window = pd.Timedelta(days=p.sr_lookback_days).value

    t_start = time.fromisoformat(p.sess_start)
    t_cut = time.fromisoformat(p.entry_cutoff)
    t_fclose = time.fromisoformat(p.force_close)
    slip = p.slippage_ticks * p.tick
    buf = p.sl_buffer_ticks * p.tick
    do_long = p.direction in ("long", "both")
    do_short = p.direction in ("short", "both")

    hours = idx.hour.values
    mins = idx.minute.values
    dow = idx.dayofweek.values

    # --- features para minería (contexto en el momento de la entrada) ---
    rng = (df1m["high"] - df1m["low"]).values
    atr = pd.Series(rng).rolling(60, min_periods=10).mean().values     # ~1h ATR (volatilidad)
    ma = df1m["close"].rolling(480, min_periods=50).mean().values      # ~8h SMA (tendencia)
    mod_long = bias1m["module_long"].values
    mod_short = bias1m["module_short"].values

    def feats(entry, sl_px, run, direction):
        mod = mod_long[i] if direction == 1 else mod_short[i]
        lvl = pdh_1m[i] if direction == 1 else pdl_1m[i]
        return {
            "hour": int(hours[i]), "dow": int(dow[i]), "run": int(run),
            "risk_pct": round(abs(entry - sl_px) / entry * 100, 4),
            "dist_module_pct": round(abs(entry - mod) / entry * 100, 4) if not np.isnan(mod) else np.nan,
            "dist_level_pct": round(abs(lvl - entry) / entry * 100, 4) if not np.isnan(lvl) else np.nan,
            "vol_pct": round(atr[i] / entry * 100, 4) if not np.isnan(atr[i]) else np.nan,
            "above_ma": int(entry > ma[i]) if not np.isnan(ma[i]) else -1,
        }

    trades = []
    pos = None
    cur_day = None
    trades_today = 0
    day_locked = False

    # estado retroceso 1m
    lrun = 0
    lex = np.nan
    lrlow = np.inf
    srun = 0
    sex = np.nan
    srhigh = -np.inf

    def reset_long():
        nonlocal lrun, lex, lrlow
        lrun = 0
        lex = np.nan
        lrlow = np.inf

    def reset_short():
        nonlocal srun, sex, srhigh
        srun = 0
        sex = np.nan
        srhigh = -np.inf

    def sr_blocks(entry, direction, t_ns):
        """True si hay un nivel S/R de alta TF pegado en contra de la entrada."""
        if not p.use_sr:
            return False
        near = entry * p.sr_near_frac
        # día previo
        if direction == 1:
            r = pdh_1m[i]
            if not np.isnan(r) and entry < r <= entry + near:
                return True
        else:
            s = pdl_1m[i]
            if not np.isnan(s) and entry - near <= s < entry:
                return True
        # pivotes 1H vigentes (confirmados y dentro de la ventana)
        if len(sr_times):
            lo_b = np.searchsorted(sr_times, t_ns - sr_window, "left")
            hi_b = sr_ptr  # solo confirmados antes de t
            for k in range(lo_b, hi_b):
                price = sr_price[k]
                kind = sr_kind[k]
                if direction == 1 and kind == 1 and entry < price <= entry + near:
                    return True
                if direction == -1 and kind == -1 and entry - near <= price < entry:
                    return True
        return False

    for i in range(n):
        ts = idx[i]
        t_ns = ts.value

        # avanzar puntero de S/R confirmados
        while sr_ptr < len(sr_times) and sr_times[sr_ptr] <= t_ns:
            sr_ptr += 1

        # reset diario
        d = dates[i]
        if d != cur_day:
            cur_day = d
            trades_today = 0
            day_locked = False

        # ---- gestión de posición abierta (desde la vela siguiente a la entrada) ----
        if pos is not None:
            tt = time(hours[i], mins[i])
            if pos["dir"] == 1:
                hit_sl = lo[i] <= pos["sl"]
                hit_tp = h[i] >= pos["tp"]
            else:
                hit_sl = h[i] >= pos["sl"]
                hit_tp = lo[i] <= pos["tp"]
            exit_price = reason = None
            if hit_sl:
                exit_price, reason = pos["sl"], "SL"
            elif hit_tp:
                exit_price, reason = pos["tp"], "TP"
            elif tt >= t_fclose:
                exit_price, reason = c[i], "EOD"
            if exit_price is not None:
                pts = (exit_price - pos["entry"]) * pos["dir"] - 2 * slip
                pnl = pts * p.point_value - p.commission_rt
                trades.append({
                    "entry_time": pos["time"], "exit_time": ts, "dir": pos["dir"],
                    "entry": pos["entry"], "exit": exit_price, "sl": pos["sl"],
                    "tp": pos["tp"], "points": pts, "pnl": pnl, "reason": reason,
                    "r_mult": round(pts / pos["risk"], 3) if pos["risk"] else 0.0,
                    **pos.get("feat", {}),
                })
                if pnl <= 0 and p.stop_after_first_loss:
                    day_locked = True
                pos = None
            continue

        tt = time(hours[i], mins[i])
        in_entry_window = (t_start <= tt <= t_cut)
        can_enter = (in_entry_window and not day_locked
                     and (not p.max_trades_per_day or trades_today < p.max_trades_per_day))

        red = c[i] < o[i]
        green = c[i] > o[i]
        doji = c[i] == o[i]

        # =================== LONG (ejecución 1m bajo sesgo 5m largo) ===================
        if do_long:
            if not la1[i]:
                reset_long()
            else:
                if red or doji:
                    lrun += 1
                    lex = h[i]                      # línea sigue el máximo (con mecha) de la última roja
                    lrlow = min(lrlow, lo[i])
                else:  # green
                    if lrun >= p.min_run_1m and not np.isnan(lex) and c[i] > lex:
                        # cuerpo cerró por encima de la línea -> ENTRADA al cierre
                        entry = c[i] + slip
                        sl_px = lrlow - buf
                        risk = entry - sl_px
                        if risk > 0 and can_enter and not sr_blocks(entry, 1, t_ns):
                            pos = {"dir": 1, "entry": entry, "sl": sl_px,
                                   "tp": entry + p.tp_ratio * risk, "risk": risk,
                                   "time": ts, "bar": i, "feat": feats(entry, sl_px, lrun, 1)}
                            trades_today += 1
                        reset_long()
                    else:
                        reset_long()  # verde que no confirma -> rompe la continuidad

        # =================== SHORT (espejo) ===================
        if do_short and pos is None:
            if not sa1[i]:
                reset_short()
            else:
                if green or doji:
                    srun += 1
                    sex = lo[i]
                    srhigh = max(srhigh, h[i])
                else:  # red
                    if srun >= p.min_run_1m and not np.isnan(sex) and c[i] < sex:
                        entry = c[i] - slip
                        sl_px = srhigh + buf
                        risk = sl_px - entry
                        if risk > 0 and can_enter and not sr_blocks(entry, -1, t_ns):
                            pos = {"dir": -1, "entry": entry, "sl": sl_px,
                                   "tp": entry - p.tp_ratio * risk, "risk": risk,
                                   "time": ts, "bar": i, "feat": feats(entry, sl_px, srun, -1)}
                            trades_today += 1
                        reset_short()
                    else:
                        reset_short()

    return summarize(p, df1m, pd.DataFrame(trades))


def summarize(p: Params, df: pd.DataFrame, tr: pd.DataFrame) -> dict:
    res = {"params": asdict(p), "bars": len(df),
           "from": str(df.index.min()), "to": str(df.index.max())}
    if tr.empty:
        res["n_trades"] = 0
        print_report(res)
        return res
    tr = tr.sort_values("exit_time").reset_index(drop=True)
    tr["equity"] = tr["pnl"].cumsum()
    wins = tr[tr["pnl"] > 0]
    losses = tr[tr["pnl"] <= 0]
    gw = wins["pnl"].sum()
    gl = -losses["pnl"].sum()
    peak = tr["equity"].cummax()
    dd = tr["equity"] - peak
    res.update({
        "n_trades": len(tr),
        "n_long": int((tr["dir"] == 1).sum()),
        "n_short": int((tr["dir"] == -1).sum()),
        "win_rate": round(len(wins) / len(tr) * 100, 1),
        "net_pnl_usd": round(tr["pnl"].sum(), 2),
        "avg_win_usd": round(wins["pnl"].mean(), 2) if len(wins) else 0.0,
        "avg_loss_usd": round(losses["pnl"].mean(), 2) if len(losses) else 0.0,
        "payoff": round(wins["pnl"].mean() / -losses["pnl"].mean(), 2) if len(losses) and len(wins) else 0.0,
        "profit_factor": round(gw / gl, 2) if gl > 0 else float("inf"),
        "max_drawdown_usd": round(dd.min(), 2),
        "expectancy_usd": round(tr["pnl"].mean(), 2),
        "tp_hits": int((tr["reason"] == "TP").sum()),
        "sl_hits": int((tr["reason"] == "SL").sum()),
        "eod_hits": int((tr["reason"] == "EOD").sum()),
    })
    tag = f"faithful_{p.symbol}_{p.direction}_tp{p.tp_ratio}_sr{int(p.use_sr)}"
    tr.to_csv(OUT / f"trades_{tag}.csv", index=False)
    res["trades_csv"] = str(OUT / f"trades_{tag}.csv")
    print_report(res)
    return res


def print_report(res: dict) -> None:
    p = res["params"]
    print("=" * 64)
    print(f"AGOTAMIENTOS FIEL  {p['symbol']}  dir={p['direction']}  TP={p['tp_ratio']}R  "
          f"1m-run>={p['min_run_1m']}  SR={p['use_sr']}")
    print(f"Periodo: {res['from']}  ->  {res['to']}  ({res['bars']} velas 1m)")
    print(f"Entradas {p['sess_start']}-{p['entry_cutoff']} ET | cierre {p['force_close']} ET | "
          f"max {p['max_trades_per_day']}/día | stop-1ª-pérdida={p['stop_after_first_loss']}")
    print("-" * 64)
    if res.get("n_trades", 0) == 0:
        print("Sin operaciones con estos parámetros.")
        print("=" * 64)
        return
    print(f"Trades: {res['n_trades']}  (long {res['n_long']} / short {res['n_short']})")
    print(f"Win rate: {res['win_rate']}%   TP/SL/EOD: {res['tp_hits']}/{res['sl_hits']}/{res['eod_hits']}")
    print(f"PnL neto: ${res['net_pnl_usd']}  [MNQ 1 contrato, con comis+slippage]")
    print(f"Profit factor: {res['profit_factor']}   Payoff: {res['payoff']}   Expectancy/trade: ${res['expectancy_usd']}")
    print(f"Avg win: ${res['avg_win_usd']}   Avg loss: ${res['avg_loss_usd']}")
    print(f"Max drawdown: ${res['max_drawdown_usd']}")
    print("=" * 64)


def build_parser() -> argparse.ArgumentParser:
    d = Params()
    ap = argparse.ArgumentParser(description="Backtest FIEL estrategia Agotamientos (5m+1m)")
    ap.add_argument("--symbol", default=d.symbol)
    ap.add_argument("--swing5m", type=int, default=d.swing5m)
    ap.add_argument("--min-run-1m", type=int, default=d.min_run_1m)
    ap.add_argument("--tp-ratio", type=float, default=d.tp_ratio)
    ap.add_argument("--sl-buffer-ticks", type=float, default=d.sl_buffer_ticks)
    ap.add_argument("--point-value", type=float, default=d.point_value)
    ap.add_argument("--commission-rt", type=float, default=d.commission_rt)
    ap.add_argument("--slippage-ticks", type=float, default=d.slippage_ticks)
    ap.add_argument("--direction", default=d.direction, choices=["long", "short", "both"])
    ap.add_argument("--sess-start", default=d.sess_start)
    ap.add_argument("--entry-cutoff", default=d.entry_cutoff)
    ap.add_argument("--force-close", default=d.force_close)
    ap.add_argument("--max-trades-per-day", type=int, default=d.max_trades_per_day)
    ap.add_argument("--no-stop-after-first-loss", action="store_true")
    ap.add_argument("--no-discipline", action="store_true",
                    help="minería: sin max/día ni stop-1ª-pérdida (toma TODOS los setups en ventana)")
    ap.add_argument("--no-sr", action="store_true", help="desactivar filtro de S/R")
    ap.add_argument("--sr-near-frac", type=float, default=d.sr_near_frac)
    return ap


if __name__ == "__main__":
    a = build_parser().parse_args()
    p = Params(
        symbol=a.symbol, swing5m=a.swing5m, min_run_1m=a.min_run_1m, tp_ratio=a.tp_ratio,
        sl_buffer_ticks=a.sl_buffer_ticks, point_value=a.point_value,
        commission_rt=a.commission_rt, slippage_ticks=a.slippage_ticks,
        direction=a.direction, sess_start=a.sess_start, entry_cutoff=a.entry_cutoff,
        force_close=a.force_close,
        max_trades_per_day=0 if a.no_discipline else a.max_trades_per_day,
        stop_after_first_loss=False if a.no_discipline else (not a.no_stop_after_first_loss),
        use_sr=not a.no_sr, sr_near_frac=a.sr_near_frac,
    )
    run(p)
