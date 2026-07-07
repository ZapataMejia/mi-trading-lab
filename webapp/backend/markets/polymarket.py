"""Adapter de datos historicos Polymarket.

Carga los CSV pre-procesados de:
  - data/poly_backtest_year/{asset}_hourly_1y_full.csv  (V1/V2B/V5 style)
  - data/poly_backtest_year/v4_real/v4_real_1y.csv      (V4 style — CLOB real)

Y cachea en memoria para que los backtests sean rapidos (~10ms cada uno
en lugar de 500ms de re-parse).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd


# Path absoluto a /data/ (asumimos cwd = repo root)
DATA_DIR = Path("data/poly_backtest_year")

ASSETS = ("btc", "eth", "sol", "xrp")


class PolymarketDataAdapter:
    """Carga y cachea la data historica de Polymarket."""

    @staticmethod
    @lru_cache(maxsize=8)
    def load_hourly_full(assets: tuple[str, ...] = ASSETS) -> pd.DataFrame:
        """Carga los hourly_1y_full.csv de los assets indicados.

        Devuelve un DataFrame concat con columnas extra: 'asset' (lowercase),
        'window_start' tz-aware UTC, 'hour', 'weekday'.
        """
        frames = []
        for a in assets:
            f = DATA_DIR / f"{a}_hourly_1y_full.csv"
            if not f.exists():
                continue
            df = pd.read_csv(f)
            df["asset"] = a
            frames.append(df)
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
        df["window_start"] = pd.to_datetime(df["window_start"], utc=True)
        df["hour"] = df["window_start"].dt.hour
        df["weekday"] = df["window_start"].dt.day_name()
        return df

    @staticmethod
    @lru_cache(maxsize=1)
    def load_v4_real() -> pd.DataFrame:
        """Carga v4_real_1y.csv (CLOB minuto-a-minuto). Tiene asset embebido."""
        f = DATA_DIR / "v4_real" / "v4_real_1y.csv"
        if not f.exists():
            return pd.DataFrame()
        df = pd.read_csv(f)
        df["window_start"] = pd.to_datetime(df["window_start"], utc=True)
        df["hour"] = df["window_start"].dt.hour
        df["weekday"] = df["window_start"].dt.day_name()
        if "asset" not in df.columns and "slug" in df.columns:
            df["asset"] = df["slug"].str.extract(r"^([a-z]+)")[0]
        return df

    @classmethod
    def load_universe(cls, dataset: str) -> pd.DataFrame:
        """Punto de entrada unico: dado un dataset key, devuelve el DF."""
        if dataset == "hourly_full":
            return cls.load_hourly_full()
        elif dataset == "v4_real":
            return cls.load_v4_real()
        else:
            raise ValueError(f"Dataset desconocido: {dataset!r}")

    @classmethod
    def info(cls) -> dict:
        """Metadata sobre los datasets disponibles."""
        hourly = cls.load_hourly_full()
        v4 = cls.load_v4_real()
        return {
            "hourly_full": {
                "rows": len(hourly),
                "assets": sorted(hourly["asset"].unique().tolist()) if not hourly.empty else [],
                "start": hourly["window_start"].min().isoformat() if not hourly.empty else None,
                "end": hourly["window_start"].max().isoformat() if not hourly.empty else None,
                "description": "1 ano de mercados pre-analizados con modelo log-normal (BTC, ETH, SOL, XRP).",
            },
            "v4_real": {
                "rows": len(v4),
                "assets": sorted(v4["asset"].unique().tolist()) if (not v4.empty and "asset" in v4.columns) else [],
                "start": v4["window_start"].min().isoformat() if not v4.empty else None,
                "end": v4["window_start"].max().isoformat() if not v4.empty else None,
                "description": "Re-fetch con CLOB minuto-a-minuto. Datos mas precisos para endgame.",
            },
        }
