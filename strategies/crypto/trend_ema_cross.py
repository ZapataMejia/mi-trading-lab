"""Trend EMA Cross — clasico cruce 12/26 con filtro EMA200.

Logica:
  - EMA fast (12) y EMA slow (26) sobre los closes.
  - Cross arriba (fast > slow tras estar igual o por debajo): long.
  - Cross abajo: short.
  - SOLO entramos en la direccion de la tendencia mayor (EMA200): long si
    close > EMA200, short si close < EMA200.
  - Salida: en el cross opuesto (pos invertida).

Default: 12/26/200 (clasico MACD-trend).
"""
from __future__ import annotations

from strategies.base import Bar, CryptoStrategy, Order, StrategyRegistry


class TrendEMACross(CryptoStrategy):
    name = "Trend · EMA 12/26 cross + EMA200 filter"
    description = (
        "Cruce de EMA 12/26 con filtro de tendencia EMA200. Solo abrimos longs "
        "por encima de la EMA200 y shorts por debajo."
    )
    tags = ("trend", "ma_cross", "crypto")

    # ----- Mercado -----
    symbol = "BTCUSDT"
    timeframe = "1h"

    # ----- Parametros estrategia -----
    fast = 12
    slow = 26
    trend = 200
    leverage = 2.0

    # ----- Engine config -----
    lookback = 250  # EMA200 necesita historia para converger

    @classmethod
    def config_dict(cls) -> dict:
        d = super().config_dict()
        d.update({
            "fast": cls.fast,
            "slow": cls.slow,
            "trend": cls.trend,
            "leverage": cls.leverage,
        })
        return d

    @staticmethod
    def _ema(values: list[float], period: int) -> float | None:
        if not values or period <= 0:
            return None
        k = 2.0 / (period + 1)
        ema = values[0]
        for v in values[1:]:
            ema = v * k + ema * (1 - k)
        return ema

    def on_bar(self, bar: Bar, state: dict) -> Order | None:
        history = list(state["history"])
        if len(history) < self.trend + 2:
            return None

        closes_now = [b.close for b in history]
        closes_prev = closes_now[:-1]

        fast_now = self._ema(closes_now, self.fast)
        slow_now = self._ema(closes_now, self.slow)
        fast_prev = self._ema(closes_prev, self.fast)
        slow_prev = self._ema(closes_prev, self.slow)
        trend_now = self._ema(closes_now, self.trend)

        if None in (fast_now, slow_now, fast_prev, slow_prev, trend_now):
            return None

        crossed_up   = fast_prev <= slow_prev and fast_now > slow_now
        crossed_down = fast_prev >= slow_prev and fast_now < slow_now

        pos = state.get("position")

        # Cierre en cross opuesto (independiente del filtro de tendencia)
        if pos is not None:
            if pos["side"] == "long" and crossed_down:
                return Order(side="close", size_usd=0.0)
            if pos["side"] == "short" and crossed_up:
                return Order(side="close", size_usd=0.0)
            return None

        # Solo abrir alineado con la EMA200
        if crossed_up and bar.close > trend_now:
            return Order(side="long", size_usd=self.stake, leverage=self.leverage)
        if crossed_down and bar.close < trend_now:
            return Order(side="short", size_usd=self.stake, leverage=self.leverage)
        return None


StrategyRegistry.register(TrendEMACross)
