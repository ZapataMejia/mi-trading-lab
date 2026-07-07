"""Interfaces base para todas las estrategias de Mi Trading Lab.

DISENO
======
Cada estrategia es una subclase con atributos de CLASE (no de instancia).
Eso permite:
  1) Descubrimiento automatico: el loader recorre /strategies/ y registra
     toda subclase de Strategy que encuentre.
  2) Sin estado mutable entre runs: cada backtest crea un dict nuevo, sin
     side-effects en la clase original.
  3) Codigo declarativo y legible — la "config" ES la clase.

EJEMPLO MINIMO (Polymarket)
---------------------------
    from strategies.base import PolymarketStrategy

    class MiNuevaEstrategia(PolymarketStrategy):
        name = "Mi nueva estrategia"
        description = "Edge >= 25pp solo lunes"
        threshold = 0.25
        only_weekdays = ("Monday",)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar


# ===========================================================================
#                              BASE Strategy
# ===========================================================================
class Strategy:
    """Clase base de toda estrategia. No instanciar directamente — usar
    PolymarketStrategy / CryptoStrategy / OptionsStrategy."""

    # ----- Metadata (override en subclases) ----------------------------------
    name: ClassVar[str] = "Untitled Strategy"
    description: ClassVar[str] = ""
    market_type: ClassVar[str] = "abstract"   # "polymarket" | "crypto_perp" | "options"
    version: ClassVar[str] = "1.0"
    author: ClassVar[str] = "Santiago"
    tags: ClassVar[tuple[str, ...]] = ()

    # ----- Defaults economicos -----------------------------------------------
    initial_bankroll: ClassVar[float] = 100.0
    stake: ClassVar[float] = 10.0
    bankroll_floor: ClassVar[float] = 30.0   # game over si bankroll < floor

    # ----- Sizing -----
    # "fixed" = apuesta `stake` USD por trade (default — bueno para medir edge).
    # "kelly" = apuesta kelly_fraction * bankroll * f_kelly_optimo, cap max_pct_per_trade.
    #           Replica el sizing del bot real en src/polymarket/paper_trader.py.
    sizing_mode: ClassVar[str] = "fixed"
    kelly_fraction: ClassVar[float] = 0.25   # cuarto-Kelly, default conservador
    max_pct_per_trade: ClassVar[float] = 0.10  # cap del 10% del bankroll
    max_position_usd: ClassVar[float] = 200.0  # tope absoluto USD (orderbook depth realista de Polymarket 1h)
    min_position_usd: ClassVar[float] = 1.0    # min order size de Polymarket

    # ----- IDs -----
    @classmethod
    def strategy_id(cls) -> str:
        """Identificador estable: 'polymarket.v1_alerts' tipo dotted-path."""
        module = cls.__module__
        if module.startswith("strategies."):
            module = module[len("strategies."):]
        return f"{module}.{cls.__name__}"

    @classmethod
    def to_dict(cls) -> dict:
        """Serializa la estrategia para la API (sin metodos)."""
        return {
            "id": cls.strategy_id(),
            "name": cls.name,
            "description": cls.description,
            "market_type": cls.market_type,
            "version": cls.version,
            "author": cls.author,
            "tags": list(cls.tags),
            "initial_bankroll": cls.initial_bankroll,
            "stake": cls.stake,
            "config": cls.config_dict(),
        }

    @classmethod
    def config_dict(cls) -> dict:
        """Override en subclases para devolver la config especifica del mercado."""
        return {}


# ===========================================================================
#                       POLYMARKET — Up/Down hourly bins
# ===========================================================================
class PolymarketStrategy(Strategy):
    """Estrategia declarativa sobre Polymarket Up/Down hourly markets.

    Cada "mercado" es una ventana de 1h (BTC, ETH, SOL, XRP). Tenemos una fila
    pre-analizada por mercado con:
      - signal_edge_up  (puede ser +/-, |edge| >= threshold = entrar)
      - p_poly_at_signal, p_fair_at_signal
      - outcome (UP/DOWN), volume_usd, hour, weekday, asset...

    La estrategia se define con filtros (threshold + skip + asset filter).
    El engine los aplica y simula cada trade con costos realistas.
    """

    market_type: ClassVar[str] = "polymarket"

    # ----- Filtros principales -----
    threshold: ClassVar[float] = 0.05               # min |edge| (5pp default)
    asset_filter: ClassVar[tuple[str, ...]] = ()    # () = todos. ('sol',) = solo SOL
    skip_hours_utc: ClassVar[tuple[int, ...]] = ()  # horas UTC para saltar
    skip_weekdays: ClassVar[tuple[str, ...]] = ()   # ('Saturday','Sunday')
    only_weekdays: ClassVar[tuple[str, ...]] = ()   # solo esos dias (vacio = todos)
    min_volume_usd: ClassVar[float] = 0.0           # filtro de liquidez
    min_seconds_to_resolution: ClassVar[int] = 30   # guard-rail para look-ahead
    max_seconds_to_resolution: ClassVar[int] = 0    # 0 = sin limite; 300 = ultimos 5min

    # ----- Que dataset usar -----
    # 'hourly_full' = data/poly_backtest_year/{asset}_hourly_1y_full.csv (V1/V2B/V5 style)
    # 'v4_real'     = data/poly_backtest_year/v4_real/v4_real_1y.csv (V4-style)
    dataset: ClassVar[str] = "hourly_full"

    # ----- Costos -----
    half_spread: ClassVar[float] = 0.015            # 1.5cents
    flat_fee: ClassVar[float] = 0.005               # 0.5cents
    fee_rate: ClassVar[float] = 0.02                # 2% taker

    @classmethod
    def config_dict(cls) -> dict:
        return {
            "threshold": cls.threshold,
            "asset_filter": list(cls.asset_filter),
            "skip_hours_utc": list(cls.skip_hours_utc),
            "skip_weekdays": list(cls.skip_weekdays),
            "only_weekdays": list(cls.only_weekdays),
            "min_volume_usd": cls.min_volume_usd,
            "min_seconds_to_resolution": cls.min_seconds_to_resolution,
            "max_seconds_to_resolution": cls.max_seconds_to_resolution,
            "dataset": cls.dataset,
            "half_spread": cls.half_spread,
            "flat_fee": cls.flat_fee,
            "fee_rate": cls.fee_rate,
            "sizing_mode": cls.sizing_mode,
            "kelly_fraction": cls.kelly_fraction,
            "max_pct_per_trade": cls.max_pct_per_trade,
            "max_position_usd": cls.max_position_usd,
            "min_position_usd": cls.min_position_usd,
        }


# ===========================================================================
#                          CRYPTO  (Spot / Perp)
# ===========================================================================
@dataclass
class Bar:
    """OHLCV bar para crypto strategies."""
    timestamp: int   # unix seconds, UTC
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Order:
    """Orden generada por el step() de una crypto strategy."""
    side: str            # "long" | "short" | "close"
    size_usd: float      # cuanto en USD comprar/vender
    leverage: float = 1.0


class CryptoStrategy(Strategy):
    """Estrategia imperativa para crypto spot/perp.

    Implementa un metodo on_bar(bar, state) que decide cuando entrar/salir.
    El engine itera bar a bar y mantiene posicion/PnL.

    A diferencia de Polymarket (declarativa), aca el usuario escribe logica
    Python real. Es mas potente pero requiere mas conocimiento.
    """

    market_type: ClassVar[str] = "crypto_perp"

    # ----- Mercado -----
    symbol: ClassVar[str] = "BTCUSDT"
    timeframe: ClassVar[str] = "1h"                 # "1m" "5m" "1h" "1d"
    exchange: ClassVar[str] = "binance"

    # ----- Costos -----
    fee_rate: ClassVar[float] = 0.0006              # 0.06% taker default
    slippage_bps: ClassVar[float] = 5.0             # 5 basis points slippage

    @classmethod
    def config_dict(cls) -> dict:
        return {
            "symbol": cls.symbol,
            "timeframe": cls.timeframe,
            "exchange": cls.exchange,
            "fee_rate": cls.fee_rate,
            "slippage_bps": cls.slippage_bps,
        }

    def on_bar(self, bar: Bar, state: dict) -> Order | None:
        """Override en subclases. Devuelve una Order o None.

        `state` es un dict mutable persistente entre llamadas con:
          - 'position': None | {'side':'long'/'short', 'entry':float, 'size_usd':float}
          - 'cash': float
          - 'history': list[Bar]  (ultimas N barras, depende de strategy.lookback)
          - cualquier cosa que la strategy quiera guardar
        """
        return None


# ===========================================================================
#                                REGISTRY
# ===========================================================================
class StrategyRegistry:
    """Singleton que mantiene el catalogo de estrategias descubiertas."""

    _registry: dict[str, type[Strategy]] = {}

    @classmethod
    def register(cls, strategy_cls: type[Strategy]) -> None:
        cls._registry[strategy_cls.strategy_id()] = strategy_cls

    @classmethod
    def get(cls, strategy_id: str) -> type[Strategy] | None:
        return cls._registry.get(strategy_id)

    @classmethod
    def all(cls) -> list[type[Strategy]]:
        return list(cls._registry.values())

    @classmethod
    def by_market(cls, market_type: str) -> list[type[Strategy]]:
        return [s for s in cls._registry.values() if s.market_type == market_type]

    @classmethod
    def clear(cls) -> None:
        cls._registry.clear()
