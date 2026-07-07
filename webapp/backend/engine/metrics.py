"""Calculo de metricas de performance.

Las metricas se computan POST backtest sobre la lista de trades y la
equity curve. Esto permite reusar las mismas formulas para cualquier
estrategia (Polymarket, crypto, options).
"""
from __future__ import annotations

import math
import statistics
from typing import Sequence

from webapp.backend.engine.types import Trade, EquityPoint


def compute_metrics(
    trades: Sequence[Trade],
    equity_curve: Sequence[EquityPoint],
    initial_bankroll: float,
) -> dict[str, float]:
    """Computa todas las metricas estandar de un backtest.

    Devuelve un dict serializable a JSON con:
      - n_trades, n_wins, n_losses, win_rate_pct
      - profit_factor
      - best_trade, worst_trade, avg_trade
      - avg_win, avg_loss
      - expectancy
      - max_drawdown_pct, max_drawdown_usd
      - sharpe (anualizado, asumiendo 1 trade/dia equivalent)
      - sortino
      - calmar
      - exposure_pct (fraction de tiempo con posicion abierta — para crypto)
      - longest_win_streak, longest_loss_streak
    """
    n = len(trades)
    if n == 0:
        return {
            "n_trades": 0, "n_wins": 0, "n_losses": 0, "win_rate_pct": 0.0,
            "profit_factor": 0.0, "best_trade": 0.0, "worst_trade": 0.0,
            "avg_trade": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            "expectancy": 0.0, "max_drawdown_pct": 0.0, "max_drawdown_usd": 0.0,
            "sharpe": 0.0, "sortino": 0.0, "calmar": 0.0,
            "longest_win_streak": 0, "longest_loss_streak": 0,
        }

    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    n_wins = len(wins)
    n_losses = len(losses)

    win_rate = (100.0 * n_wins / n) if n else 0.0

    sum_wins = sum(wins)
    sum_losses = abs(sum(losses))
    profit_factor = (sum_wins / sum_losses) if sum_losses > 0 else float("inf") if sum_wins > 0 else 0.0

    avg_win = (sum_wins / n_wins) if n_wins else 0.0
    avg_loss = (-sum_losses / n_losses) if n_losses else 0.0
    avg_trade = sum(pnls) / n
    expectancy = (win_rate / 100.0) * avg_win + (1 - win_rate / 100.0) * avg_loss

    # Drawdown desde equity curve
    max_dd_pct = 0.0
    max_dd_usd = 0.0
    peak_bankroll = initial_bankroll
    for pt in equity_curve:
        peak_bankroll = max(peak_bankroll, pt.bankroll)
        dd_usd = pt.bankroll - peak_bankroll
        dd_pct = (dd_usd / peak_bankroll * 100) if peak_bankroll > 0 else 0.0
        if dd_pct < max_dd_pct:
            max_dd_pct = dd_pct
        if dd_usd < max_dd_usd:
            max_dd_usd = dd_usd

    # Sharpe / Sortino — sobre pnls por trade
    # Para Sortino, downside es el desvio de retornos NEGATIVOS (versus 0, no versus mean).
    if n > 1:
        mean_pnl = avg_trade
        std_pnl = statistics.stdev(pnls)
        sharpe = (mean_pnl / std_pnl * math.sqrt(252)) if std_pnl > 0 else 0.0
        # Sortino: standard deviation of the DOWNSIDE returns (clipped at 0)
        downside_dev_sq = sum(min(p, 0.0) ** 2 for p in pnls) / n
        downside_dev = math.sqrt(downside_dev_sq) if downside_dev_sq > 0 else 0.0
        sortino = (mean_pnl / downside_dev * math.sqrt(252)) if downside_dev > 0 else 0.0
    else:
        sharpe = 0.0
        sortino = 0.0

    # Calmar = total return / |max DD|
    total_return_pct = ((equity_curve[-1].bankroll - initial_bankroll) / initial_bankroll * 100) if equity_curve else 0.0
    calmar = (total_return_pct / abs(max_dd_pct)) if max_dd_pct < 0 else 0.0

    # Streaks
    longest_win_streak = 0
    longest_loss_streak = 0
    current_win = 0
    current_loss = 0
    for t in trades:
        if t.is_winner:
            current_win += 1
            current_loss = 0
            longest_win_streak = max(longest_win_streak, current_win)
        else:
            current_loss += 1
            current_win = 0
            longest_loss_streak = max(longest_loss_streak, current_loss)

    return {
        "n_trades":           n,
        "n_wins":             n_wins,
        "n_losses":           n_losses,
        "win_rate_pct":       round(win_rate, 2),
        "profit_factor":      round(profit_factor, 3) if profit_factor != float("inf") else None,
        "best_trade":         round(max(pnls), 2),
        "worst_trade":        round(min(pnls), 2),
        "avg_trade":          round(avg_trade, 3),
        "avg_win":            round(avg_win, 3),
        "avg_loss":           round(avg_loss, 3),
        "expectancy":         round(expectancy, 4),
        "max_drawdown_pct":   round(max_dd_pct, 2),
        "max_drawdown_usd":   round(max_dd_usd, 2),
        "sharpe":             round(sharpe, 2),
        "sortino":            round(sortino, 2),
        "calmar":             round(calmar, 2),
        "longest_win_streak": longest_win_streak,
        "longest_loss_streak": longest_loss_streak,
    }
