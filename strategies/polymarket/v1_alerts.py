"""V1 Alerts — la base sin filtros."""
from strategies.base import PolymarketStrategy, StrategyRegistry


class V1Alerts(PolymarketStrategy):
    name = "V1 · Alerts"
    description = "Edge ≥ 5pp, sin filtros, 24/7. La estrategia mas agresiva, opera el bot original."
    threshold = 0.05
    dataset = "hourly_full"
    tags = ("baseline", "live", "agresiva")


StrategyRegistry.register(V1Alerts)
