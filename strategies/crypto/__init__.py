"""Estrategias crypto — perpetuos / spot.

Cada archivo aca define una subclase de CryptoStrategy. Al importar este
modulo se auto-registran en StrategyRegistry (porque cada strategy llama
StrategyRegistry.register(...) al final de su modulo).
"""
from strategies.crypto import (
    breakout_donchian,
    mean_reversion_zscore,
    trend_ema_cross,
)

__all__ = [
    "breakout_donchian",
    "mean_reversion_zscore",
    "trend_ema_cross",
]
