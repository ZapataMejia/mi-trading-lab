"""Tipos compartidos del engine de backtest."""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any


@dataclass
class Trade:
    """Un trade ejecutado en el backtest."""
    timestamp: str             # ISO 8601 UTC
    asset: str                 # 'btc' | 'eth' | 'sol' | ...
    direction: str             # 'UP'/'DOWN' (polymarket), 'long'/'short' (crypto)
    entry_price: float         # fill price (con spread incluido)
    exit_price: float          # payoff (0 o 1 en poly, exit price en crypto)
    stake_usd: float
    cost_paid: float           # entry_price * size + fees
    pnl: float
    is_winner: bool
    bankroll_after: float
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EquityPoint:
    """Snapshot del bankroll en el tiempo."""
    timestamp: str
    bankroll: float
    pnl_cumulative: float
    trades_to_date: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BacktestResult:
    """Resultado completo de un backtest."""
    strategy_id: str
    strategy_name: str
    market_type: str
    period_start: str
    period_end: str
    initial_bankroll: float
    final_bankroll: float
    total_pnl: float
    total_pnl_pct: float
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[EquityPoint] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    game_over_at: str | None = None
    skipped_markets: int = 0
    candidate_markets: int = 0
    config_used: dict = field(default_factory=dict)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "market_type": self.market_type,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "initial_bankroll": self.initial_bankroll,
            "final_bankroll": self.final_bankroll,
            "total_pnl": self.total_pnl,
            "total_pnl_pct": self.total_pnl_pct,
            "trades": [t.to_dict() for t in self.trades],
            "equity_curve": [e.to_dict() for e in self.equity_curve],
            "metrics": self.metrics,
            "game_over_at": self.game_over_at,
            "skipped_markets": self.skipped_markets,
            "candidate_markets": self.candidate_markets,
            "config_used": self.config_used,
            "duration_seconds": self.duration_seconds,
        }

    def summary(self) -> dict:
        """Version reducida (sin trades ni equity curve) para listados rapidos."""
        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "market_type": self.market_type,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "initial_bankroll": self.initial_bankroll,
            "final_bankroll": self.final_bankroll,
            "total_pnl": self.total_pnl,
            "total_pnl_pct": self.total_pnl_pct,
            "n_trades": len(self.trades),
            "metrics": self.metrics,
        }
