"""V4A Endgame 30pp — entra solo en los ultimos 5 minutos de cada mercado."""
from strategies.base import PolymarketStrategy, StrategyRegistry


class V4AEndgame30pp(PolymarketStrategy):
    name = "V4A · Endgame 30pp"
    description = "Edge ≥ 30pp, solo ultimos 5 minutos antes de la resolucion. Backtested con CLOB real."
    threshold = 0.30
    max_seconds_to_resolution = 300   # ultimos 5 min
    min_seconds_to_resolution = 30
    dataset = "v4_real"
    tags = ("endgame", "live", "high-wr")


StrategyRegistry.register(V4AEndgame30pp)
