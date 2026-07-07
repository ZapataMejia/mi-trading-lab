"""TEMPLATE — Una nueva estrategia Polymarket en 10 lineas.

Copia este archivo a `strategies/polymarket/mi_estrategia.py`, cambia el
nombre de la clase y los filtros, y aparecera automaticamente en la web
app la proxima vez que reinicies el backend (o presiones "Recargar").

Importante: AGREGA tu nueva estrategia al __init__.py de polymarket/ para
que se importe automaticamente.
"""
from strategies.base import PolymarketStrategy, StrategyRegistry


class MiEstrategiaTemplate(PolymarketStrategy):
    # --- Metadata ---
    name = "Mi estrategia template"
    description = "Edge 15pp, solo lunes y martes, mercados de >$10k volumen"
    tags = ("template", "ejemplo")

    # --- Filtros ---
    threshold = 0.15                          # 15 pp minimo de edge
    only_weekdays = ("Monday", "Tuesday")     # solo lunes y martes
    min_volume_usd = 10000.0                  # mercados con >= $10k
    # asset_filter = ("btc", "eth")           # descomentar para solo BTC+ETH
    # skip_hours_utc = (0, 1, 2)              # descomentar para skip madrugada UTC

    # --- Dataset ---
    # 'hourly_full' = data historica 1 ano completa (V1/V2B/V5 style)
    # 'v4_real'     = data CLOB minuto-a-minuto (V4 style, mas precisa)
    dataset = "hourly_full"


StrategyRegistry.register(MiEstrategiaTemplate)
