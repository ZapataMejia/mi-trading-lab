"""FastAPI entrypoint de Mi Trading Lab.

Run con:
    cd /Users/santiago/Documents/Personal/trading
    source .venv/bin/activate
    uvicorn webapp.backend.main:app --reload --port 8000

Despues abrir http://localhost:8000/docs para ver el API.
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from webapp.backend.api import advanced_api, assistant_api, backtest_api, fondeo_api, strategies_api

try:
    from webapp.backend.api import live_bots_api
except ImportError:
    live_bots_api = None  # src/ no incluido en deploy mínimo (p. ej. PythonAnywhere)
from webapp.backend.loader import load_all_strategies

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)

app = FastAPI(
    title="Mi Trading Lab",
    description="API local para descubrir y backtestear estrategias.",
    version="0.1.0",
)

_default_origins = "http://localhost:3000,http://127.0.0.1:3000"
_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", _default_origins).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cargar estrategias al startup
@app.on_event("startup")
def _startup() -> None:
    n = load_all_strategies()
    logging.getLogger("webapp.main").info("Mi Trading Lab arrancado con %d estrategias", n)


# Healthcheck
@app.get("/")
def root() -> dict:
    from strategies.base import StrategyRegistry
    return {
        "name": "Mi Trading Lab",
        "version": "0.1.0",
        "strategies_loaded": len(StrategyRegistry.all()),
        "docs": "/docs",
    }


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/capabilities")
def capabilities() -> dict:
    """Qué módulos funcionan en este despliegue (local vs nube)."""
    import os

    from webapp.backend.markets.forex import ForexDataAdapter
    from webapp.backend.markets.polymarket import PolymarketDataAdapter

    forex_ok = False
    try:
        r = ForexDataAdapter.data_range("EURUSD", "M5")
        forex_ok = bool(r.get("available") and r.get("date_from") and r.get("date_to"))
    except Exception:
        pass

    poly_ok = not PolymarketDataAdapter.load_hourly_full().empty
    crypto_ok = os.getenv("ENABLE_CRYPTO_BACKTEST", "1").strip().lower() in ("1", "true", "yes")

    from webapp.backend.api.fondeo_api import max_sim_days_for_ui

    return {
        "forex": forex_ok,
        "polymarket": poly_ok,
        "crypto": crypto_ok,
        "online_mode": os.getenv("ONLINE_MODE", "0").strip().lower() in ("1", "true", "yes"),
        "max_sim_days": max_sim_days_for_ui(),
    }


app.include_router(strategies_api.router)
app.include_router(backtest_api.router)
if live_bots_api is not None:
    app.include_router(live_bots_api.router)
app.include_router(advanced_api.router)
app.include_router(fondeo_api.router)
app.include_router(assistant_api.router)
