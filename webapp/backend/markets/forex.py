"""Adapter de datos forex (CSV local + descarga Yahoo para arranque rápido)."""
from __future__ import annotations

import bisect
import io
import json
import logging
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger("webapp.markets.forex")

CACHE_DIR = Path("data/forex_cache")
_TS_INDEX_STEP = 5000
_WARMUP_DAYS = 3

# Yahoo Finance chart API (sin API key, datos recientes)
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"


def _normalize_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    # SQX export: Date (yyyyMMdd) + Time (HH:mm:ss) — tratar antes del rename genérico
    colmap = {c.strip().lower(): c for c in df.columns}
    if "date" in colmap and "time" in colmap:
        out = df.rename(columns={
            colmap["date"]: "date",
            colmap["time"]: "time",
            **{colmap[k]: k for k in ("open", "high", "low", "close", "volume") if k in colmap},
        })
        out["timestamp"] = pd.to_datetime(
            out["date"].astype(str).str.strip() + " " + out["time"].astype(str).str.strip(),
            format="%Y%m%d %H:%M:%S",
            utc=True,
            errors="coerce",
        )
        out = out.drop(columns=["date", "time"], errors="ignore")
    else:
        out = df.copy()

    rename: dict[str, str] = {}
    for c in out.columns:
        if c == "timestamp":
            continue
        cl = c.strip().lower()
        if cl in ("timestamp", "datetime"):
            rename[c] = "timestamp"
        elif cl in ("date",) and "timestamp" not in out.columns:
            rename[c] = "timestamp"
        elif cl in ("open", "o"):
            rename[c] = "open"
        elif cl in ("high", "h"):
            rename[c] = "high"
        elif cl in ("low", "l"):
            rename[c] = "low"
        elif cl in ("close", "c"):
            rename[c] = "close"
        elif cl in ("volume", "vol", "v"):
            rename[c] = "volume"
    out = out.rename(columns=rename)

    if "timestamp" not in out.columns and isinstance(df.index, pd.DatetimeIndex):
        out = out.reset_index().rename(columns={"index": "timestamp"})

    required = ["timestamp", "open", "high", "low", "close"]
    for col in required:
        if col not in out.columns:
            raise ValueError(f"CSV sin columna requerida: {col}")

    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    for col in ("open", "high", "low", "close"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    if "volume" not in out.columns:
        out["volume"] = 0.0
    else:
        out["volume"] = pd.to_numeric(out["volume"], errors="coerce").fillna(0)

    out = out.dropna(subset=["open", "high", "low", "close"])
    return out[["timestamp", "open", "high", "low", "close", "volume"]].sort_values("timestamp")


class ForexDataAdapter:
    """Carga OHLCV forex desde cache CSV o Yahoo Finance."""

    SYMBOL_MAP = {
        "EURUSD": "EURUSD=X",
        "GBPUSD": "GBPUSD=X",
        "USDJPY": "USDJPY=X",
    }

    @classmethod
    def _ts_index_path(cls, path: Path) -> Path:
        return Path(str(path) + ".tsidx")

    @classmethod
    def _ensure_ts_index(cls, path: Path) -> dict:
        """Índice sparse (cada N filas) para leer solo el rango de fechas pedido."""
        idx_path = cls._ts_index_path(path)
        if idx_path.is_file():
            try:
                return json.loads(idx_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        entries: list[list] = []
        row = 0
        with path.open(encoding="utf-8", errors="replace") as f:
            f.readline()  # header
            for line in f:
                if row % _TS_INDEX_STEP == 0:
                    ts_raw = line.split(",", 1)[0].strip()
                    entries.append([row, pd.to_datetime(ts_raw, utc=True).isoformat()])
                row += 1

        payload = {"step": _TS_INDEX_STEP, "rows": row, "entries": entries}
        idx_path.write_text(json.dumps(payload), encoding="utf-8")
        logger.info("Forex: índice temporal creado %s (%d filas)", idx_path.name, row)
        return payload

    @classmethod
    def _row_at_or_after(cls, index: dict, target: pd.Timestamp) -> int:
        entries = index["entries"]
        if not entries:
            return 0
        stamps = [pd.Timestamp(e[1]) for e in entries]
        pos = bisect.bisect_left(stamps, target)
        if pos >= len(entries):
            return index["rows"]
        return max(0, entries[pos][0])

    @classmethod
    def _row_at_or_before(cls, index: dict, target: pd.Timestamp) -> int:
        entries = index["entries"]
        if not entries:
            return 0
        stamps = [pd.Timestamp(e[1]) for e in entries]
        pos = bisect.bisect_right(stamps, target) - 1
        if pos < 0:
            return 0
        start_row = entries[pos][0]
        # La entrada sparse puede estar antes del target; avanzar hasta el final del bloque.
        next_row = entries[pos + 1][0] if pos + 1 < len(entries) else index["rows"]
        return min(index["rows"] - 1, next_row - 1)

    @classmethod
    def _load_csv_range(cls, path: Path, start: str, end: str) -> pd.DataFrame:
        start_ts = pd.to_datetime(start, utc=True) - pd.Timedelta(days=_WARMUP_DAYS)
        end_ts = pd.to_datetime(end, utc=True)
        if len(str(end).strip()) <= 10:
            end_ts = end_ts + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

        index = cls._ensure_ts_index(path)
        row_start = cls._row_at_or_after(index, start_ts)
        row_end = cls._row_at_or_before(index, end_ts)
        if row_start > row_end:
            return pd.DataFrame()

        nrows = row_end - row_start + 1
        df = pd.read_csv(
            path,
            skiprows=range(1, row_start + 1),
            nrows=nrows,
            encoding="utf-8",
            on_bad_lines="skip",
        )
        df = _normalize_ohlc(df)
        df = df[(df["timestamp"] >= start_ts) & (df["timestamp"] <= end_ts)]
        logger.info(
            "Forex: rango %s → %s = %d barras (filas %d–%d de %d)",
            start,
            end,
            len(df),
            row_start,
            row_end,
            index["rows"],
        )
        return df.sort_values("timestamp").reset_index(drop=True)

    @classmethod
    def cache_path(cls, symbol: str, timeframe: str) -> Path:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return CACHE_DIR / f"{symbol}_{timeframe}.csv"

    @classmethod
    def _csv_date_range(cls, path: Path) -> tuple[str | None, str | None]:
        """Primera y última fecha del CSV sin cargar todo el archivo."""
        try:
            first = pd.read_csv(path, nrows=1)
            if first.empty:
                return None, None
            t0 = pd.to_datetime(first.iloc[0, 0], utc=True)
            with path.open("rb") as f:
                f.seek(0, 2)
                pos = f.tell()
                chunk = b""
                while pos > 0:
                    step = min(8192, pos)
                    pos -= step
                    f.seek(pos)
                    chunk = f.read(step) + chunk
                    if chunk.count(b"\n") > 1:
                        break
                last_line = chunk.splitlines()[-1].decode("utf-8", errors="ignore")
            t1 = pd.to_datetime(last_line.split(",")[0], utc=True)
            return t0.strftime("%Y-%m-%d"), t1.strftime("%Y-%m-%d")
        except Exception:
            return None, None

    @classmethod
    def data_range(cls, symbol: str = "EURUSD", timeframe: str = "M5") -> dict:
        path = cls.cache_path(symbol, timeframe)
        if not path.exists():
            return {"symbol": symbol, "timeframe": timeframe, "available": False}
        d0, d1 = cls._csv_date_range(path)
        idx_path = cls._ts_index_path(path)
        if idx_path.is_file():
            try:
                rows = int(json.loads(idx_path.read_text(encoding="utf-8")).get("rows", 0))
            except Exception:
                rows = sum(1 for _ in path.open()) - 1
        else:
            rows = sum(1 for _ in path.open()) - 1
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "available": d0 is not None,
            "date_from": d0,
            "date_to": d1,
            "rows": max(0, rows),
            "path": str(path),
        }

    @classmethod
    def info(cls) -> dict:
        caches = []
        if CACHE_DIR.exists():
            for p in sorted(CACHE_DIR.glob("*.csv")):
                try:
                    df = pd.read_csv(p, nrows=0)
                    d0, d1 = cls._csv_date_range(p)
                    idx_path = cls._ts_index_path(p)
                    if idx_path.is_file():
                        try:
                            rows = int(json.loads(idx_path.read_text(encoding="utf-8")).get("rows", 0))
                        except Exception:
                            rows = sum(1 for _ in p.open()) - 1
                    else:
                        rows = sum(1 for _ in p.open()) - 1
                    caches.append({
                        "file": p.name,
                        "path": str(p),
                        "rows": max(0, rows),
                        "columns": list(df.columns),
                        "date_from": d0,
                        "date_to": d1,
                    })
                except Exception:
                    caches.append({"file": p.name, "path": str(p), "rows": 0, "columns": []})
        return {
            "cache_dir": str(CACHE_DIR),
            "cached_files": caches,
            "supported_symbols": list(cls.SYMBOL_MAP.keys()),
            "timeframes": ["M5"],
            "csv_format": "timestamp, open, high, low, close [, volume]",
            "note": "Para historial largo (como Dukascopy en SQX), exporta CSV a data/forex_cache/EURUSD_M5.csv",
        }

    @classmethod
    def load_csv(cls, path: Path | str) -> pd.DataFrame:
        df = pd.read_csv(path)
        return _normalize_ohlc(df)

    @classmethod
    def load_from_upload(cls, content: bytes) -> pd.DataFrame:
        df = pd.read_csv(io.BytesIO(content))
        return _normalize_ohlc(df)

    @classmethod
    def save_cache(cls, df: pd.DataFrame, symbol: str, timeframe: str) -> Path:
        path = cls.cache_path(symbol, timeframe)
        df.to_csv(path, index=False)
        return path

    @classmethod
    def _fetch_stooq(cls, symbol: str, start: str, end: str) -> pd.DataFrame:
        """Stooq CSV — historial M5 sin API key."""
        sym = symbol.lower()
        d1 = pd.to_datetime(start).strftime("%Y%m%d")
        d2 = pd.to_datetime(end).strftime("%Y%m%d")
        url = f"https://stooq.com/q/d/l/?s={sym}&d1={d1}&d2={d2}&i=5m"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; TradingLab/1.0)"}
        resp = requests.get(url, headers=headers, timeout=60)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        if df.empty:
            return df
        # Stooq: Date (YYYYMMDD), Time, Open, High, Low, Close, Volume
        colmap = {c: c.lower() for c in df.columns}
        df = df.rename(columns=colmap)
        if "date" in df.columns and "time" in df.columns:
            df["timestamp"] = pd.to_datetime(
                df["date"].astype(str).str.zfill(8) + " " + df["time"].astype(str),
                format="%Y%m%d %H:%M:%S",
                utc=True,
                errors="coerce",
            )
        return _normalize_ohlc(df)

    @classmethod
    def _fetch_yahoo(cls, symbol: str, interval: str, range_: str) -> pd.DataFrame:
        ticker = cls.SYMBOL_MAP.get(symbol.upper(), f"{symbol}=X")
        params = {"interval": interval, "range": range_}
        headers = {"User-Agent": "Mozilla/5.0 (compatible; TradingLab/1.0)"}
        resp = requests.get(YAHOO_CHART.format(ticker=ticker), params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        result = resp.json()["chart"]["result"][0]
        ts = result["timestamp"]
        q = result["indicators"]["quote"][0]
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(ts, unit="s", utc=True),
            "open": q["open"],
            "high": q["high"],
            "low": q["low"],
            "close": q["close"],
            "volume": q.get("volume") or [0] * len(ts),
        })
        return df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

    @classmethod
    def load_bars(
        cls,
        symbol: str = "EURUSD",
        timeframe: str = "M5",
        start: str | None = None,
        end: str | None = None,
        prefer_cache: bool = True,
    ) -> pd.DataFrame:
        path = cls.cache_path(symbol, timeframe)
        df: pd.DataFrame | None = None

        if prefer_cache and path.exists():
            try:
                if start and end:
                    df = cls._load_csv_range(path, start, end)
                else:
                    index = cls._ensure_ts_index(path)
                    if index["rows"] > 80000:
                        raise ValueError(
                            f"CSV grande ({index['rows']:,} barras): indica period_start y period_end"
                        )
                    df = cls.load_csv(path)
                logger.info("Forex: cargado cache %s (%d barras)", path, len(df))
            except Exception as exc:
                logger.warning("Cache forex corrupto %s: %s", path, exc)
                raise RuntimeError(f"Error leyendo {path}: {exc}") from exc

        if df is None or df.empty:
            if path.exists():
                raise RuntimeError(
                    f"Sin barras forex para {symbol} entre {start} y {end}. "
                    f"Revisa las fechas o el CSV en {path}."
                )
            end_dt = pd.Timestamp.now(tz="UTC")
            start_dt = end_dt - pd.Timedelta(days=365)
            logger.info("Forex: descargando %s M5 desde Stooq (%s -> %s)...", symbol, start_dt.date(), end_dt.date())
            try:
                df = cls._fetch_stooq(symbol, start_dt.isoformat(), end_dt.isoformat())
                if df.empty:
                    raise ValueError("Stooq devolvio vacio")
                cls.save_cache(df, symbol, timeframe)
            except Exception as exc:
                logger.warning("Stooq fallo (%s), probando Yahoo...", exc)
                try:
                    df = cls._fetch_yahoo(symbol, interval="5m", range_="60d")
                    cls.save_cache(df, symbol, timeframe)
                except Exception as exc2:
                    raise RuntimeError(
                        f"No hay datos forex para {symbol}. Sube un CSV a {path}. ({exc2})"
                    ) from exc2

        if not (start and end):
            if start:
                df = df[df["timestamp"] >= pd.to_datetime(start, utc=True)]
            if end:
                end_ts = pd.to_datetime(end, utc=True)
                if len(str(end).strip()) <= 10:
                    end_ts = end_ts + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
                df = df[df["timestamp"] <= end_ts]
        return df.sort_values("timestamp").reset_index(drop=True)
