"""Mean Reversion via Z-Score — fade de extremos estadisticos.

Logica:
  - Calcula el z-score del close vs la media de las ultimas N barras.
  - z < -2  -> long  (precio "barato")
  - z > +2  -> short (precio "caro")
  - Cuando z vuelve a 0, cerramos la posicion.

Default: lookback=50 (sweet-spot empirico para crypto 1h).
"""
from __future__ import annotations

from strategies.base import Bar, CryptoStrategy, Order, StrategyRegistry


class MeanReversionZScore(CryptoStrategy):
    name = "Mean Reversion · Z-Score 50"
    description = (
        "Fade de extremos: long si zscore < -2, short si zscore > +2. Salida cuando "
        "el zscore vuelve a 0. Lookback de 50 barras."
    )
    tags = ("mean_reversion", "stat_arb", "crypto")

    # ----- Mercado -----
    symbol = "BTCUSDT"
    timeframe = "1h"

    # ----- Parametros estrategia -----
    lookback_bars = 50
    z_entry = 2.0
    z_exit = 0.0
    leverage = 2.0

    # ----- Engine config -----
    lookback = 60   # >= lookback_bars + cushion

    @classmethod
    def config_dict(cls) -> dict:
        d = super().config_dict()
        d.update({
            "lookback_bars": cls.lookback_bars,
            "z_entry": cls.z_entry,
            "z_exit": cls.z_exit,
            "leverage": cls.leverage,
        })
        return d

    def on_bar(self, bar: Bar, state: dict) -> Order | None:
        history = list(state["history"])
        if len(history) < self.lookback_bars + 1:
            return None

        closes = [b.close for b in history[-self.lookback_bars:]]
        n = len(closes)
        mean = sum(closes) / n
        var = sum((c - mean) ** 2 for c in closes) / n
        std = var ** 0.5
        if std <= 0:
            return None
        z = (bar.close - mean) / std

        pos = state.get("position")

        # Salidas: cuando z cruza el nivel z_exit (0 por default)
        if pos is not None:
            if pos["side"] == "long" and z >= self.z_exit:
                return Order(side="close", size_usd=0.0)
            if pos["side"] == "short" and z <= -self.z_exit:
                return Order(side="close", size_usd=0.0)
            return None

        # Entradas
        if z < -self.z_entry:
            return Order(side="long", size_usd=self.stake, leverage=self.leverage)
        if z > self.z_entry:
            return Order(side="short", size_usd=self.stake, leverage=self.leverage)
        return None


StrategyRegistry.register(MeanReversionZScore)
