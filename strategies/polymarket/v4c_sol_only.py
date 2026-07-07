"""V4C SOL-only — V4A pero limitado a mercados Solana (mejor WR historico)."""
from strategies.base import PolymarketStrategy, StrategyRegistry


class V4CSOLOnly(PolymarketStrategy):
    name = "V4C · SOL-only Endgame"
    description = "Edge ≥ 30pp en SOL, ultimos 5 min. SOL mostro 67%+ WR en el backtest."
    threshold = 0.30
    asset_filter = ("sol",)
    max_seconds_to_resolution = 300
    min_seconds_to_resolution = 30
    dataset = "v4_real"
    tags = ("endgame", "sol", "nicho")


StrategyRegistry.register(V4CSOLOnly)
