"""Adapter de datos crypto (Binance perpetuos / spot).

Carga klines (OHLCV) desde el endpoint publico de Binance:
  - perpetuos USDT-M (default): https://fapi.binance.com/fapi/v1/klines
  - spot:                       https://api.binance.com/api/v3/klines

Cachea en memoria via @lru_cache y persiste un CSV en
`data/crypto_cache/{symbol}_{timeframe}.csv` que se usa como fallback si
la red falla.

Uso:
    from webapp.backend.markets.crypto import CryptoDataAdapter
    df = CryptoDataAdapter.load_klines("BTCUSDT", "1h", "2024-01-01", "2024-06-01")
"""
from __future__ import annotations

import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import requests

logger = logging.getLogger("webapp.markets.crypto")

# Endpoints publicos (no requieren API key)
FUTURES_URL = "https://fapi.binance.com/fapi/v1/klines"   # USDT-M perpetuos
SPOT_URL    = "https://api.binance.com/api/v3/klines"     # spot

CACHE_DIR = Path("data/crypto_cache")

# Conversion timeframe -> ms (todos los intervalos validos de Binance)
_TF_MS = {
    "1m":     60_000,
    "3m":    180_000,
    "5m":    300_000,
    "15m":   900_000,
    "30m": 1_800_000,
    "1h":  3_600_000,
    "2h":  7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h":43_200_000,
    "1d": 86_400_000,
    "3d":259_200_000,
    "1w":604_800_000,
}


def _to_ms(value: Any) -> int:
    """Convierte ISO date/datetime/Timestamp a ms epoch UTC."""
    ts = pd.to_datetime(value, utc=True)
    return int(ts.value // 1_000_000)


class CryptoDataAdapter:
    """Carga klines de Binance perpetual futures (default) o spot."""

    REQUEST_TIMEOUT = 20.0
    PAGE_LIMIT_PERP = 1500   # max fapi
    PAGE_LIMIT_SPOT = 1000   # max spot api

    # ------------------------------------------------------------------
    #  Disco
    # ------------------------------------------------------------------
    @classmethod
    def _cache_path(cls, symbol: str, timeframe: str) -> Path:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return CACHE_DIR / f"{symbol}_{timeframe}.csv"

    @classmethod
    def _save_disk_cache(cls, df: pd.DataFrame, symbol: str, timeframe: str) -> None:
        if df is None or df.empty:
            return
        path = cls._cache_path(symbol, timeframe)
        try:
            if path.exists():
                old = pd.read_csv(path)
                old["timestamp"] = pd.to_datetime(old["timestamp"], utc=True)
                merged = pd.concat([old, df], ignore_index=True)
                merged = merged.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
                merged.to_csv(path, index=False)
                return
        except Exception as exc:
            logger.warning("No se pudo merger cache existente %s: %s", path, exc)
        df.to_csv(path, index=False)

    @classmethod
    def _read_disk_cache(cls, symbol: str, timeframe: str, start_ms: int, end_ms: int) -> pd.DataFrame:
        path = cls._cache_path(symbol, timeframe)
        if not path.exists():
            return pd.DataFrame()
        try:
            df = pd.read_csv(path)
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            # Comparamos contra Timestamps directamente (independiente de la
            # resolucion ns/us del dtype, que cambia entre versiones de pandas).
            start_ts = pd.Timestamp(start_ms, unit="ms", tz="UTC")
            end_ts = pd.Timestamp(end_ms, unit="ms", tz="UTC")
            df = df[(df["timestamp"] >= start_ts) & (df["timestamp"] <= end_ts)]
            return df.sort_values("timestamp").reset_index(drop=True)
        except Exception as exc:
            logger.warning("Cache local corrupto %s: %s", path, exc)
            return pd.DataFrame()

    # ------------------------------------------------------------------
    #  Red
    # ------------------------------------------------------------------
    @classmethod
    def _fetch_page(cls, symbol: str, timeframe: str, start_ms: int, end_ms: int, market: str) -> list[list]:
        if market == "spot":
            url, limit = SPOT_URL, cls.PAGE_LIMIT_SPOT
        else:
            url, limit = FUTURES_URL, cls.PAGE_LIMIT_PERP
        params = {
            "symbol": symbol,
            "interval": timeframe,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": limit,
        }
        r = requests.get(url, params=params, timeout=cls.REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()

    @classmethod
    def _fetch_paginated(cls, symbol: str, timeframe: str, start_ms: int, end_ms: int, market: str) -> pd.DataFrame:
        if timeframe not in _TF_MS:
            raise ValueError(f"Timeframe no soportado: {timeframe!r}")
        step_ms = _TF_MS[timeframe]
        page_limit = cls.PAGE_LIMIT_SPOT if market == "spot" else cls.PAGE_LIMIT_PERP
        rows: list[list] = []
        cursor = start_ms
        pages = 0
        while cursor < end_ms:
            page = cls._fetch_page(symbol, timeframe, cursor, end_ms, market)
            pages += 1
            if not page:
                break
            rows.extend(page)
            last_open_ms = page[-1][0]
            new_cursor = last_open_ms + step_ms
            if new_cursor <= cursor:
                break  # safety: nunca avanzariamos
            cursor = new_cursor
            if len(page) < page_limit:
                break
            time.sleep(0.05)  # gentle rate limiting (~1200 req/min)
        logger.info(
            "Binance %s %s %s -> %d klines (%d pages)",
            market, symbol, timeframe, len(rows), pages,
        )
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore",
        ])
        df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        for c in ("open", "high", "low", "close", "volume"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        df = df.dropna(subset=["close"])
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        return df

    # ------------------------------------------------------------------
    #  API publica
    # ------------------------------------------------------------------
    @classmethod
    @lru_cache(maxsize=64)
    def load_klines(
        cls,
        symbol: str,
        timeframe: str = "1h",
        start: str = "2024-01-01",
        end: str | None = None,
        market: str = "perp",
    ) -> pd.DataFrame:
        """Devuelve OHLCV con columnas: timestamp (UTC), open, high, low, close, volume.

        Args:
            symbol:    'BTCUSDT', 'ETHUSDT', etc.
            timeframe: '1m','5m','15m','30m','1h','4h','1d',...
            start:     ISO date/datetime (UTC).
            end:       ISO date/datetime (UTC). Por default = ahora.
            market:    'perp' (default, fapi) o 'spot'.
        """
        if end is None:
            end = pd.Timestamp.utcnow().isoformat()
        start_ms = _to_ms(start)
        end_ms = _to_ms(end)
        if end_ms <= start_ms:
            raise ValueError(f"end ({end}) debe ser posterior a start ({start})")

        try:
            df = cls._fetch_paginated(symbol, timeframe, start_ms, end_ms, market)
            if not df.empty:
                cls._save_disk_cache(df, symbol, timeframe)
                return df
            logger.warning(
                "Binance devolvio 0 klines para %s %s — fallback a cache local", symbol, timeframe,
            )
            return cls._read_disk_cache(symbol, timeframe, start_ms, end_ms)
        except Exception as exc:
            logger.warning(
                "Fetch Binance fallo (%s) — fallback a cache local %s_%s.csv",
                exc, symbol, timeframe,
            )
            cached = cls._read_disk_cache(symbol, timeframe, start_ms, end_ms)
            if cached.empty:
                raise RuntimeError(
                    f"No pude obtener klines de Binance ni del cache local: {exc}"
                ) from exc
            return cached

    @classmethod
    def cache_clear(cls) -> None:
        """Limpia el lru_cache (util al re-fetchear)."""
        cls.load_klines.cache_clear()
