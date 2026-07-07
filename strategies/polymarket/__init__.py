"""Estrategias Polymarket — Up/Down hourly markets.

Cada archivo aca define una subclase de PolymarketStrategy. Al importar
este modulo se auto-registran en StrategyRegistry.
"""
from strategies.polymarket import (
    v1_alerts,
    v2b_selective,
    v4a_endgame_30pp,
    v4b_endgame_40pp,
    v4c_sol_only,
)

__all__ = [
    "v1_alerts",
    "v2b_selective",
    "v4a_endgame_30pp",
    "v4b_endgame_40pp",
    "v4c_sol_only",
]
