"""V4B Endgame 40pp — version mas estricta de V4A."""
from strategies.base import PolymarketStrategy, StrategyRegistry


class V4BEndgame40pp(PolymarketStrategy):
    name = "V4B · Endgame 40pp"
    description = "Edge ≥ 40pp, ultimos 5 minutos. Menos trades pero mayor WR esperado."
    threshold = 0.40
    max_seconds_to_resolution = 300
    min_seconds_to_resolution = 30
    dataset = "v4_real"
    tags = ("endgame", "live", "tight")


StrategyRegistry.register(V4BEndgame40pp)
