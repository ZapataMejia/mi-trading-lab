"""Mi Trading Lab — Strategies registry.

Las estrategias viven aca, organizadas por tipo de mercado:
  - polymarket/  → estrategias para Polymarket Up/Down hourly markets
  - crypto/      → estrategias para crypto spot/perp (Binance, Bybit...)
  - options/     → (futuro) estrategias para options
  - _examples/   → templates y ejemplos para arrancar una nueva

El loader del backend (webapp/backend/loader.py) descubre automaticamente
todas las subclases de strategies.base.Strategy en estas carpetas y las
expone via API.
"""
from strategies.base import Strategy, PolymarketStrategy, CryptoStrategy, StrategyRegistry

__all__ = ["Strategy", "PolymarketStrategy", "CryptoStrategy", "StrategyRegistry"]
