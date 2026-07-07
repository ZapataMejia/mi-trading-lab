"""Endpoint para leer el estado live de los bots paper-trading.

Reusa la logica del Telegram dashboard_bot.py — lee directamente los
state.json de los 5 bots. Asi el frontend puede mostrar lo mismo que
el Telegram bot pero con grafico.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter

from src.polymarket.dashboard_bot import BOTS, load_bot_metrics

router = APIRouter(prefix="/api/live", tags=["live"])

ROOT = Path(".")


@router.get("/bots")
def list_live_bots() -> dict:
    """Devuelve el estado actual de los 5 bots paper-trading (leyendo state.json)."""
    out = []
    total_bankroll = 0.0
    total_initial = 0.0
    total_pnl_total = 0.0
    total_pnl_today = 0.0
    total_pnl_week = 0.0
    total_open = 0
    total_closed = 0
    total_trades_today = 0

    for bot in BOTS:
        m = load_bot_metrics(bot, ROOT)
        if m is None:
            out.append({
                "label": bot.label,
                "name": bot.name,
                "emoji": bot.emoji,
                "threshold_pp": bot.threshold_pp,
                "description": bot.description,
                "alive": False,
                "error": "state.json no encontrado o ilegible",
            })
            continue

        d = asdict(m)
        d["pct_change_total"] = m.pct_change_total
        d["alive"] = True
        d["name"] = bot.name
        d["threshold_pp"] = bot.threshold_pp
        d["description"] = bot.description
        d["state_path"] = str(bot.state_path)
        out.append(d)

        total_bankroll += m.bankroll
        total_initial += m.initial_bankroll
        total_pnl_total += m.pnl_total
        total_pnl_today += m.pnl_today
        total_pnl_week += m.pnl_week
        total_open += m.open_positions
        total_closed += m.closed_total
        total_trades_today += m.trades_today

    summary = {
        "total_bankroll": round(total_bankroll, 2),
        "total_initial": round(total_initial, 2),
        "total_pnl_total": round(total_pnl_total, 2),
        "total_pnl_today": round(total_pnl_today, 2),
        "total_pnl_week": round(total_pnl_week, 2),
        "total_open_positions": total_open,
        "total_closed_positions": total_closed,
        "total_trades_today": total_trades_today,
        "n_alive": sum(1 for b in out if b.get("alive")),
        "n_total": len(BOTS),
    }

    return {
        "bots": out,
        "summary": summary,
    }


@router.get("/bots/{label}/trades")
def bot_trades(label: str, limit: int = 100) -> dict:
    """Devuelve los ultimos N trades cerrados de un bot especifico."""
    import json

    bot = next((b for b in BOTS if b.label.lower() == label.lower()), None)
    if not bot:
        return {"error": f"Bot {label} no existe", "trades": []}
    path = ROOT / bot.state_path
    if not path.exists():
        return {"error": "state.json no encontrado", "trades": []}
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        return {"error": str(exc), "trades": []}

    closed = data.get("closed_positions", []) or []
    sorted_closed = sorted(closed, key=lambda p: p.get("settled_at_utc") or "", reverse=True)
    trimmed = sorted_closed[:limit]

    out_trades = []
    for pos in trimmed:
        out_trades.append({
            "asset": pos.get("asset", "?"),
            "direction": pos.get("direction", "?"),
            "edge": pos.get("edge_entry"),
            "p_poly": pos.get("p_poly_entry"),
            "p_fair": pos.get("p_fair_entry"),
            "fill": pos.get("fill_price"),
            "stake_usd": pos.get("position_usd"),
            "cost_paid": pos.get("cost_paid"),
            "pnl": pos.get("pnl"),
            "correct": pos.get("correct"),
            "opened_at_utc": pos.get("opened_at_utc"),
            "settled_at_utc": pos.get("settled_at_utc"),
            "slug": pos.get("slug"),
        })

    return {"label": bot.label, "trades": out_trades, "total_closed": len(closed)}
