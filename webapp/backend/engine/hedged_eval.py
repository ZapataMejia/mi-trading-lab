"""Simulación hedge 2 cuentas WS — cuenta A natural, cuenta B espejo (curso HobbyCode)."""
from __future__ import annotations

import time as time_lib
from dataclasses import dataclass
from typing import Any

import pandas as pd

from webapp.backend.engine.fondeo_engine import (
    FondeoConfig,
    _apply_slippage,
    _day_key,
    _in_session,
    _position_size,
)
from webapp.backend.engine.metrics import compute_metrics
from webapp.backend.engine.types import BacktestResult, EquityPoint, Trade
from webapp.backend.engine.ws_eval import WS_CLASSIC_5K, evaluate_ws_classic


@dataclass
class HedgedPairResult:
    account_a: BacktestResult
    account_b: BacktestResult
    outcome: str
    winner: str | None
    days_to_win: int | None
    stopped_reason: str

    def to_dict(self) -> dict[str, Any]:
        cfg_dict = self.account_a.config_used
        cfg = FondeoConfig(**{k: cfg_dict[k] for k in FondeoConfig.__dataclass_fields__})
        ev_a = evaluate_ws_classic(self.account_a, cfg)
        ev_b = evaluate_ws_classic(self.account_b, cfg)
        return {
            "outcome": self.outcome,
            "winner": self.winner,
            "days_to_win": self.days_to_win,
            "stopped_reason": self.stopped_reason,
            "account_a": _acct_payload("Cuenta A (dirección natural)", self.account_a, ev_a),
            "account_b": _acct_payload("Cuenta B (espejo inverso)", self.account_b, ev_b),
            "equity_a": [{"timestamp": p.timestamp, "bankroll": p.bankroll, "pnl": p.pnl_cumulative} for p in self.account_a.equity_curve[-300:]],
            "equity_b": [{"timestamp": p.timestamp, "bankroll": p.bankroll, "pnl": p.pnl_cumulative} for p in self.account_b.equity_curve[-300:]],
            "summary": _pair_summary(self.outcome, self.winner, self.days_to_win, ev_a, ev_b),
            "config": cfg_dict,
        }


def _acct_payload(label: str, result: BacktestResult, ev: dict) -> dict:
    return {
        "label": label,
        "total_pnl": result.total_pnl,
        "total_pnl_pct": result.total_pnl_pct,
        "final_bankroll": result.final_bankroll,
        "n_trades": result.metrics["n_trades"],
        "max_drawdown_pct": result.metrics["max_drawdown_pct"],
        "ws_eval": ev,
    }


def _pair_summary(outcome: str, winner: str | None, days: int | None, ev_a: dict, ev_b: dict) -> str:
    if outcome == "a_wins":
        return f"Hedge OK — Cuenta A pasa eval en {days}d. B termina {ev_b['static_dd_pct']}% DD."
    if outcome == "b_wins":
        return f"Hedge OK — Cuenta B pasa eval en {days}d. A termina {ev_a['static_dd_pct']}% DD."
    if outcome == "both_fail":
        return f"Par falla — A {ev_a['static_dd_pct']}% · B {ev_b['static_dd_pct']}%."
    return "Ventana terminada sin pasar eval en ninguna cuenta."


def _make_result(
    cfg: FondeoConfig,
    symbol: str,
    balance: float,
    trades: list[Trade],
    equity: list[EquityPoint],
    t0: float,
    p_start: str,
    p_end: str,
) -> BacktestResult:
    metrics = compute_metrics(trades, equity, cfg.initial_balance)
    if metrics.get("profit_factor") == float("inf"):
        metrics["profit_factor"] = 999.0
    return BacktestResult(
        strategy_id="fondeo.hedge",
        strategy_name="Fondeo Hedge Pair",
        market_type="forex",
        period_start=p_start,
        period_end=p_end,
        initial_bankroll=cfg.initial_balance,
        final_bankroll=round(balance, 2),
        total_pnl=round(balance - cfg.initial_balance, 2),
        total_pnl_pct=round((balance - cfg.initial_balance) / cfg.initial_balance * 100, 2),
        trades=trades,
        equity_curve=equity,
        metrics=metrics,
        config_used=cfg.to_dict(),
        duration_seconds=round(time_lib.time() - t0, 4),
    )


def _breached_static(balance: float, initial: float) -> bool:
    return balance <= initial * (1.0 - WS_CLASSIC_5K["max_static_dd_pct"] / 100.0)


def _unrealized(pos: dict[str, Any], price: float) -> float:
    direction = pos["direction"]
    entry = pos["entry"]
    notional = pos["notional"]
    if direction == "long":
        return notional * (price - entry) / entry
    return notional * (entry - price) / entry


def _equity(balance: float, pos: dict[str, Any] | None, price: float) -> float:
    if pos is None:
        return balance
    return balance + _unrealized(pos, price)


def _best_equity(balance: float, pos: dict[str, Any] | None, h: float, l: float) -> float:
    if pos is None:
        return balance
    return _equity(balance, pos, h if pos["direction"] == "long" else l)


def _worst_equity(balance: float, pos: dict[str, Any] | None, h: float, l: float) -> float:
    if pos is None:
        return balance
    return _equity(balance, pos, l if pos["direction"] == "long" else h)


def _close_one_pos(
    pos: dict[str, Any],
    balance: float,
    exit_price: float,
    ts: pd.Timestamp,
    reason: str,
    account: str,
    symbol: str,
    commission_usd: float,
) -> tuple[float, Trade]:
    direction = pos["direction"]
    entry = pos["entry"]
    notional = pos["notional"]
    if direction == "long":
        pnl = notional * (exit_price - entry) / entry
    else:
        pnl = notional * (entry - exit_price) / entry
    pnl -= commission_usd
    balance += pnl
    return balance, Trade(
        timestamp=ts.isoformat(),
        asset="EURUSD",
        direction=direction,
        entry_price=round(entry, 5),
        exit_price=round(exit_price, 5),
        stake_usd=round(notional, 2),
        cost_paid=round(notional, 2),
        pnl=round(pnl, 2),
        is_winner=pnl > 0,
        bankroll_after=round(balance, 2),
        extra={"reason": reason, "account": account},
    )


def _resolve_outcome(
    bal_a: float,
    bal_b: float,
    trades_a: list[Trade],
    trades_b: list[Trade],
    eq_a: list[EquityPoint],
    eq_b: list[EquityPoint],
    cfg: FondeoConfig,
    symbol: str,
    t0: float,
    p_start: str,
    p_end: str,
) -> HedgedPairResult:
    res_a = _make_result(cfg, symbol, bal_a, trades_a, eq_a, t0, p_start, p_end)
    res_b = _make_result(cfg, symbol, bal_b, trades_b, eq_b, t0, p_start, p_end)
    ev_a = evaluate_ws_classic(res_a, cfg)
    ev_b = evaluate_ws_classic(res_b, cfg)
    initial = cfg.initial_balance

    if ev_a["checks"]["pass_all"]:
        return HedgedPairResult(res_a, res_b, "a_wins", "A", ev_a["days_to_meta"], "pass_all_a")
    if ev_b["checks"]["pass_all"]:
        return HedgedPairResult(res_a, res_b, "b_wins", "B", ev_b["days_to_meta"], "pass_all_b")
    if _breached_static(bal_a, initial) and _breached_static(bal_b, initial):
        return HedgedPairResult(res_a, res_b, "both_fail", None, None, "both_static_dd")
    return HedgedPairResult(res_a, res_b, "timeout", None, None, "incomplete")


def run_hedged_backtest(
    bars: pd.DataFrame,
    cfg: FondeoConfig,
    symbol: str = "EURUSD",
    commission_usd: float = 5.0,
    stop_at_meta: bool = True,
    use_mid_prices: bool = True,
    equity_guardian: bool = True,
) -> HedgedPairResult:
    """Cuenta A = señal natural; cuenta B = dirección invertida en cada cruce.

    equity_guardian: para al +8% equity (incl. flotante), como el copiador del curso.
    """
    t0 = time_lib.time()
    if bars is None or bars.empty:
        empty = _make_result(cfg, symbol, cfg.initial_balance, [], [], t0, "", "")
        return HedgedPairResult(empty, empty, "both_fail", None, None, "no_data")

    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)

    slip = cfg.slippage_pips * cfg.pip_size

    def entry_price(c: float, direction: str) -> float:
        if use_mid_prices:
            return c
        return _apply_slippage(c, direction, "entry", slip)

    def exit_price(price: float, direction: str) -> float:
        if use_mid_prices:
            return price
        return _apply_slippage(price, direction, "exit", slip)
    need = max(cfg.fast_period, cfg.slow_period) + 2
    offset = cfg.broker_utc_offset_hours
    sample = max(1, cfg.equity_sample_bars)
    initial = float(cfg.initial_balance)

    k_f = 2.0 / (cfg.fast_period + 1.0)
    k_s = 2.0 / (cfg.slow_period + 1.0)
    risk_frac = cfg.risk_pct / 100.0
    tp_frac = risk_frac * cfg.tp_ratio

    ema_fast = ema_slow = float("nan")
    prev_ema_fast = prev_ema_slow = float("nan")
    bars_seen = 0
    day_key = -1
    trades_today = 0

    bal_a = bal_b = initial
    pos_a: dict[str, Any] | None = None
    pos_b: dict[str, Any] | None = None
    trades_a: list[Trade] = []
    trades_b: list[Trade] = []
    eq_a: list[EquityPoint] = []
    eq_b: list[EquityPoint] = []

    meta_usd = WS_CLASSIC_5K["meta_usd"]
    floor = initial * (1.0 - WS_CLASSIC_5K["max_static_dd_pct"] / 100.0)

    def snap(ts: pd.Timestamp, mark: float) -> None:
        eq_a_val = _equity(bal_a, pos_a, mark)
        eq_b_val = _equity(bal_b, pos_b, mark)
        eq_a.append(EquityPoint(ts.isoformat(), round(eq_a_val, 2), round(eq_a_val - initial, 2), len(trades_a)))
        eq_b.append(EquityPoint(ts.isoformat(), round(eq_b_val, 2), round(eq_b_val - initial, 2), len(trades_b)))

    def close_one(
        pos: dict[str, Any],
        balance: float,
        exit_p: float,
        ts: pd.Timestamp,
        reason: str,
        account: str,
    ) -> tuple[float, Trade]:
        return _close_one_pos(pos, balance, exit_p, ts, reason, account, symbol, commission_usd)

    def try_exit(pos: dict[str, Any] | None, bal: float, account: str, h: float, l: float, c: float, ts: pd.Timestamp):
        if pos is None:
            return bal, pos, None
        direction = pos["direction"]
        sl, tp = pos["sl"], pos["tp"]
        exit_p, reason = None, ""
        in_sess = _in_session(ts, cfg.sess_start, cfg.sess_end, offset)
        if direction == "long":
            if l <= sl:
                exit_p, reason = exit_price(sl, "long"), "sl"
            elif h >= tp:
                exit_p, reason = exit_price(tp, "long"), "tp"
            elif not in_sess:
                exit_p, reason = exit_price(c, "long"), "session"
        else:
            if h >= sl:
                exit_p, reason = exit_price(sl, "short"), "sl"
            elif l <= tp:
                exit_p, reason = exit_price(tp, "short"), "tp"
            elif not in_sess:
                exit_p, reason = exit_price(c, "short"), "session"
        if exit_p is None:
            return bal, pos, None
        bal, tr = close_one(pos, bal, exit_p, ts, reason, account)
        return bal, None, tr

    t0_ts: pd.Timestamp | None = None
    p_start = df["timestamp"].iloc[0].isoformat()
    p_end = df["timestamp"].iloc[-1].isoformat()

    for row in df.itertuples(index=False):
        ts = row.timestamp
        if t0_ts is None:
            t0_ts = ts
        h, l, c = float(row.high), float(row.low), float(row.close)

        bal_a, pos_a, tr_a = try_exit(pos_a, bal_a, "A", h, l, c, ts)
        if tr_a:
            trades_a.append(tr_a)
        bal_b, pos_b, tr_b = try_exit(pos_b, bal_b, "B", h, l, c, ts)
        if tr_b:
            trades_b.append(tr_b)

        bars_seen += 1
        prev_ema_fast, prev_ema_slow = ema_fast, ema_slow
        if pd.isna(ema_fast):
            ema_fast = ema_slow = c
            if bars_seen % sample == 0:
                snap(ts, c)
            continue
        ema_fast = c * k_f + ema_fast * (1.0 - k_f)
        ema_slow = c * k_s + ema_slow * (1.0 - k_s)
        if pd.isna(prev_ema_fast):
            if bars_seen % sample == 0:
                snap(ts, c)
            continue

        dk = _day_key(ts, offset)
        if dk != day_key:
            day_key = dk
            trades_today = 0

        cross_up = prev_ema_fast <= prev_ema_slow and ema_fast > ema_slow
        cross_dn = prev_ema_fast >= prev_ema_slow and ema_fast < ema_slow

        if (
            bars_seen >= need
            and _in_session(ts, cfg.sess_start, cfg.sess_end, offset)
            and trades_today < cfg.max_trades_per_day
            and pos_a is None
            and pos_b is None
        ):
            if cross_up:
                sl_a, tp_a = c * (1.0 - risk_frac), c * (1.0 + tp_frac)
                sl_b, tp_b = c * (1.0 + risk_frac), c * (1.0 - tp_frac)
                if sl_a > 0 and tp_a > c and tp_b > 0 and sl_b > c:
                    entry_a = entry_price(c, "long")
                    entry_b = entry_price(c, "short")
                    na = _position_size(bal_a, entry_a, sl_a, cfg.mm_risk_pct)
                    nb = _position_size(bal_b, entry_b, sl_b, cfg.mm_risk_pct)
                    if na > 0 and nb > 0:
                        pos_a = {"direction": "long", "entry": entry_a, "sl": sl_a, "tp": tp_a, "notional": na}
                        pos_b = {"direction": "short", "entry": entry_b, "sl": sl_b, "tp": tp_b, "notional": nb}
                        trades_today += 1
            elif cross_dn:
                sl_a, tp_a = c * (1.0 + risk_frac), c * (1.0 - tp_frac)
                sl_b, tp_b = c * (1.0 - risk_frac), c * (1.0 + tp_frac)
                if tp_a > 0 and sl_a > c and sl_b > 0 and tp_b > c:
                    entry_a = entry_price(c, "short")
                    entry_b = entry_price(c, "long")
                    na = _position_size(bal_a, entry_a, sl_a, cfg.mm_risk_pct)
                    nb = _position_size(bal_b, entry_b, sl_b, cfg.mm_risk_pct)
                    if na > 0 and nb > 0:
                        pos_a = {"direction": "short", "entry": entry_a, "sl": sl_a, "tp": tp_a, "notional": na}
                        pos_b = {"direction": "long", "entry": entry_b, "sl": sl_b, "tp": tp_b, "notional": nb}
                        trades_today += 1

        if bars_seen % sample == 0:
            snap(ts, c)

        best_a = _best_equity(bal_a, pos_a, h, l)
        best_b = _best_equity(bal_b, pos_b, h, l)
        worst_a = _worst_equity(bal_a, pos_a, h, l)
        worst_b = _worst_equity(bal_b, pos_b, h, l)
        dead_a = worst_a <= floor
        dead_b = worst_b <= floor

        if stop_at_meta and equity_guardian and t0_ts is not None:
            hit_a = best_a - initial >= meta_usd
            hit_b = best_b - initial >= meta_usd
            if hit_a or hit_b:
                days = max(0, (ts - t0_ts).days)
                if pos_a is not None:
                    bal_a, tr = close_one(pos_a, bal_a, exit_price(c, pos_a["direction"]), ts, "guardian_meta", "A")
                    trades_a.append(tr)
                    pos_a = None
                if pos_b is not None:
                    bal_b, tr = close_one(pos_b, bal_b, exit_price(c, pos_b["direction"]), ts, "guardian_meta", "B")
                    trades_b.append(tr)
                    pos_b = None
                snap(ts, c)
                res_a = _make_result(cfg, symbol, bal_a, trades_a, eq_a, t0, p_start, p_end)
                res_b = _make_result(cfg, symbol, bal_b, trades_b, eq_b, t0, p_start, p_end)
                if hit_a and not dead_a:
                    return HedgedPairResult(res_a, res_b, "a_wins", "A", days, "guardian_meta_a")
                if hit_b and not dead_b:
                    return HedgedPairResult(res_a, res_b, "b_wins", "B", days, "guardian_meta_b")
                return HedgedPairResult(res_a, res_b, "both_fail", None, days, "guardian_both_dead")

        meta_a = bal_a - initial >= meta_usd
        meta_b = bal_b - initial >= meta_usd

        if stop_at_meta and not equity_guardian and t0_ts is not None and (meta_a or meta_b):
            days = max(0, (ts - t0_ts).days)
            res_a = _make_result(cfg, symbol, bal_a, trades_a, eq_a, t0, p_start, p_end)
            res_b = _make_result(cfg, symbol, bal_b, trades_b, eq_b, t0, p_start, p_end)
            if meta_a and not dead_a:
                return HedgedPairResult(res_a, res_b, "a_wins", "A", days, "meta_a")
            if meta_b and not dead_b:
                return HedgedPairResult(res_a, res_b, "b_wins", "B", days, "meta_b")
            if dead_a and dead_b:
                return HedgedPairResult(res_a, res_b, "both_fail", None, days, "both_dead_at_meta")

        if dead_a and dead_b:
            res_a = _make_result(cfg, symbol, bal_a, trades_a, eq_a, t0, p_start, p_end)
            res_b = _make_result(cfg, symbol, bal_b, trades_b, eq_b, t0, p_start, p_end)
            return HedgedPairResult(res_a, res_b, "both_fail", None, None, "both_static_dd")

    last = df.iloc[-1]
    ts = last["timestamp"]
    c = float(last["close"])
    if pos_a is not None:
        d = pos_a["direction"]
        bal_a, tr = close_one(pos_a, bal_a, exit_price(c, d), ts, "eod", "A")
        trades_a.append(tr)
    if pos_b is not None:
        d = pos_b["direction"]
        bal_b, tr = close_one(pos_b, bal_b, exit_price(c, d), ts, "eod", "B")
        trades_b.append(tr)
    snap(ts, c)
    return _resolve_outcome(bal_a, bal_b, trades_a, trades_b, eq_a, eq_b, cfg, symbol, t0, p_start, p_end)


@dataclass
class HedgedWindowResult:
    window_days: int
    attempts: int
    pair_wins: int
    pass_rate_pct: float
    median_days: int | None
    a_wins: int
    b_wins: int
    both_fail: int


def simulate_hedged_windows(
    bars: pd.DataFrame,
    cfg: FondeoConfig,
    window_days: int = 14,
    start: str = "2017-01-03",
    end: str = "2021-06-01",
    step: str = "2MS",
    commission_usd: float = 5.0,
) -> HedgedWindowResult:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    starts = pd.date_range(start, end, freq=step, tz="UTC")

    wins = a_w = b_w = fail = 0
    total = 0
    days_list: list[int] = []

    for s in starts:
        e = s + pd.Timedelta(days=window_days)
        chunk = df[(df["timestamp"] >= s) & (df["timestamp"] < e)]
        if len(chunk) < 500:
            continue
        total += 1
        r = run_hedged_backtest(chunk, cfg, commission_usd=commission_usd)
        if r.outcome == "a_wins":
            a_w += 1
            wins += 1
            if r.days_to_win is not None:
                days_list.append(r.days_to_win)
        elif r.outcome == "b_wins":
            b_w += 1
            wins += 1
            if r.days_to_win is not None:
                days_list.append(r.days_to_win)
        else:
            fail += 1

    med = sorted(days_list)[len(days_list) // 2] if days_list else None
    rate = round(100.0 * wins / total, 1) if total else 0.0
    return HedgedWindowResult(window_days, total, wins, rate, med, a_w, b_w, fail)
