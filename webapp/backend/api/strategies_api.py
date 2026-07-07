"""Endpoints relacionados a estrategias."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from strategies.base import StrategyRegistry
from webapp.backend.loader import reload_all_strategies

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.get("")
def list_strategies(market_type: str | None = None) -> dict:
    """Lista todas las estrategias registradas (opcionalmente filtradas por market)."""
    if market_type:
        strats = StrategyRegistry.by_market(market_type)
    else:
        strats = StrategyRegistry.all()
    return {
        "count": len(strats),
        "strategies": [s.to_dict() for s in strats],
    }


@router.get("/{strategy_id:path}")
def get_strategy(strategy_id: str) -> dict:
    """Detalle de una estrategia. strategy_id usa formato 'polymarket.v1_alerts.V1Alerts'."""
    s = StrategyRegistry.get(strategy_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Strategy not found: {strategy_id}")
    return s.to_dict()


@router.post("/reload")
def reload_strategies() -> dict:
    """Re-descubre estrategias desde /strategies/. Util cuando Claude crea una nueva."""
    n = reload_all_strategies()
    return {"loaded": n}
