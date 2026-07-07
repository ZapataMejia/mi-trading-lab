"""Indicadores técnicos compartidos (ADX, ATR)."""
from __future__ import annotations


def adx(highs: list[float], lows: list[float], closes: list[float], period: int) -> float:
    if len(closes) < period + 2:
        return 0.0
    trs, plus_dm, minus_dm = [], [], []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        trs.append(tr)
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    n = period
    atr = sum(trs[:n])
    pdm = sum(plus_dm[:n])
    mdm = sum(minus_dm[:n])
    if atr <= 0:
        return 0.0
    for i in range(n, len(trs)):
        atr = atr - atr / n + trs[i]
        pdm = pdm - pdm / n + plus_dm[i]
        mdm = mdm - mdm / n + minus_dm[i]
    if atr <= 0:
        return 0.0
    pdi = 100 * pdm / atr
    mdi = 100 * mdm / atr
    if pdi + mdi <= 0:
        return 0.0
    return 100 * abs(pdi - mdi) / (pdi + mdi)


def atr_pips(highs: list[float], lows: list[float], closes: list[float], period: int, pip_size: float) -> float:
    if len(closes) < period + 1 or pip_size <= 0:
        return 0.0
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    if len(trs) < period:
        return 0.0
    val = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        val = val - val / period + trs[i]
    return val / pip_size
