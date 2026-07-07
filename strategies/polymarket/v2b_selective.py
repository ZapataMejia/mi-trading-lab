"""V2B Selective — version con filtros de horario, dia y volumen."""
from strategies.base import PolymarketStrategy, StrategyRegistry


class V2BSelective(PolymarketStrategy):
    name = "V2B · Selective"
    description = "Edge ≥ 10pp, skip 21/23 UTC, skip sabado, volumen mínimo $5k."
    threshold = 0.10
    skip_hours_utc = (21, 23)
    skip_weekdays = ("Saturday",)
    min_volume_usd = 5000.0
    dataset = "hourly_full"
    tags = ("selectiva", "live")


StrategyRegistry.register(V2BSelective)
