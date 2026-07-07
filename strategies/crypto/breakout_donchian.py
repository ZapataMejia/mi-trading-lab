"""Donchian Channel Breakout — entrada en ruptura de extremos de N barras.

Logica:
  - Long  si bar.close > max(high) de las N barras anteriores.
  - Short si bar.close < min(low)  de las N barras anteriores.
  - Stop dinamico en el midpoint: si el close vuelve para el otro lado del
    midpoint de la ventana Donchian, cerramos.

Default: N=20 (Donchian estandar para crypto en 1h).
"""
from __future__ import annotations

from strategies.base import Bar, CryptoStrategy, Order, StrategyRegistry


class BreakoutDonchian(CryptoStrategy):
    name = "Breakout · Donchian 20"
    description = (
        "Long si cierra por encima del high de N barras; short si cierra por debajo "
        "del low. Stop en el midpoint del canal."
    )
    tags = ("breakout", "trend_following", "crypto")

    # ----- Mercado -----
    symbol = "BTCUSDT"
    timeframe = "1h"

    # ----- Parametros estrategia -----
    n_bars = 20
    leverage = 2.0

    # ----- Engine config -----
    lookback = 25  # >= n_bars + 1 (le decimos al engine cuanta history mantener)

    @classmethod
    def config_dict(cls) -> dict:
        d = super().config_dict()
        d.update({
            "n_bars": cls.n_bars,
            "leverage": cls.leverage,
        })
        return d

    def on_bar(self, bar: Bar, state: dict) -> Order | None:
        history = list(state["history"])
        # +1 porque history[-1] es la barra ACTUAL (ya appendeada por el engine)
        if len(history) < self.n_bars + 1:
            return None

        past = history[-(self.n_bars + 1):-1]   # las N anteriores (sin la actual)
        donch_high = max(b.high for b in past)
        donch_low  = min(b.low  for b in past)
        donch_mid  = (donch_high + donch_low) / 2.0

        pos = state.get("position")

        # Stop dinamico: si la posicion abierta cruza el midpoint, salimos
        if pos is not None:
            if pos["side"] == "long" and bar.close < donch_mid:
                return Order(side="close", size_usd=0.0)
            if pos["side"] == "short" and bar.close > donch_mid:
                return Order(side="close", size_usd=0.0)

        # Entradas en ruptura
        if bar.close > donch_high:
            if pos is None or pos["side"] != "long":
                return Order(side="long", size_usd=self.stake, leverage=self.leverage)
        elif bar.close < donch_low:
            if pos is None or pos["side"] != "short":
                return Order(side="short", size_usd=self.stake, leverage=self.leverage)

        return None


StrategyRegistry.register(BreakoutDonchian)
