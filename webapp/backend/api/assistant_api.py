"""Asistente del lab — respuestas guiadas (sin Cursor)."""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)


class ChatAction(BaseModel):
    type: str
    label: str
    href: str | None = None


class ChatResponse(BaseModel):
    reply: str
    actions: list[ChatAction] = Field(default_factory=list)


def _norm(text: str) -> str:
    return text.lower().strip()


def _reply_for(message: str) -> ChatResponse:
    t = _norm(message)

    if any(w in t for w in ("hola", "ayuda", "help", "empezar", "cómo", "como")):
        return ChatResponse(
            reply=(
                "Hola. Soy el asistente del **Mi Trading Lab**.\n\n"
                "Puedo explicarte la estrategia **Liquidity Sweep**, ayudarte a abrir el simulador "
                "y decirte qué periodo probar. **No creo estrategias nuevas desde cero** — eso lo "
                "desarrolla Santiago en el código (Cursor). Aquí pruebas las que ya están listas."
            ),
            actions=[
                ChatAction(type="navigate", label="Abrir Liquidity Sweep", href="/fondeo/liquidity-sweep"),
                ChatAction(type="navigate", label="Ver Lab Forex", href="/lab?mercado=forex"),
            ],
        )

    if any(w in t for w in ("liquidity", "sweep", "barrido", "liquidez", "ws", "fondeo", "5k")):
        return ChatResponse(
            reply=(
                "**Liquidity Sweep SAFE** opera en **EURUSD**, velas de **5 minutos**.\n\n"
                "Busca cuando el precio barre un máximo/mínimo reciente y cierra del otro lado; "
                "entra en contra con stop y objetivo automáticos.\n\n"
                "Config recomendada: riesgo **1,5%**, **1 trade/día**, sesión **07:00–14:00**."
            ),
            actions=[
                ChatAction(type="navigate", label="Probar en simulador", href="/fondeo/liquidity-sweep"),
                ChatAction(
                    type="navigate",
                    label="Ver gráfico (Mar 2026)",
                    href="/fondeo/liquidity-sweep?preset=q1-2026",
                ),
            ],
        )

    if any(w in t for w in ("5 min", "5min", "m5", "temporal", "timeframe", "vela")):
        return ChatResponse(
            reply=(
                "Esta estrategia está calibrada para **M5 (5 minutos)**. "
                "En el simulador verás el selector de temporalidad; por ahora solo **M5** tiene datos completos.\n\n"
                "Cambiar a M15/H1 sin re-optimizar no garantiza los mismos resultados."
            ),
            actions=[
                ChatAction(type="navigate", label="Ir al simulador", href="/fondeo/liquidity-sweep"),
            ],
        )

    if re.search(r"2026|marzo|enero|febrero|mes", t):
        return ChatResponse(
            reply=(
                "Para ver **resultados mes a mes** y el **gráfico con compras/ventas**, "
                "elige un periodo de **2026** (por ejemplo Ene–Mar 2026).\n\n"
                "Periodos largos (2022–2024) muestran el resumen anual, no el desglose mensual ni el gráfico detallado."
            ),
            actions=[
                ChatAction(
                    type="navigate",
                    label="Abrir Ene–Mar 2026",
                    href="/fondeo/liquidity-sweep?preset=q1-2026",
                ),
            ],
        )

    if any(w in t for w in ("crear", "nueva estrategia", "inventar", "cursor", "código", "codigo")):
        return ChatResponse(
            reply=(
                "Crear una **estrategia nueva** (código, reglas, backtest) requiere desarrollo — "
                "lo hace Santiago con **Cursor** en el repositorio.\n\n"
                "Este chat **no está conectado a Cursor** (es solo para ti en el IDE). "
                "Tu hermana puede **probar y entender** las estrategias ya publicadas aquí.\n\n"
                "Si tiene una idea, que te la cuente y tú la implementas en el lab."
            ),
            actions=[
                ChatAction(type="navigate", label="Probar Liquidity Sweep", href="/fondeo/liquidity-sweep"),
            ],
        )

    if any(w in t for w in ("grafico", "gráfico", "compra", "vende", "visual")):
        return ChatResponse(
            reply=(
                "El **gráfico de operaciones** (triángulos verde=compra, rojo=venta) "
                "solo aparece en periodos **cortos** (hasta ~45 días).\n\n"
                "Prueba **Ene–Mar 2026** o un solo mes del desglose."
            ),
            actions=[
                ChatAction(
                    type="navigate",
                    label="Ver gráfico Mar 2026",
                    href="/fondeo/liquidity-sweep?preset=q1-2026",
                ),
            ],
        )

    return ChatResponse(
        reply=(
            "No estoy seguro de eso. Prueba preguntarme:\n"
            "· *¿Qué es Liquidity Sweep?*\n"
            "· *Quiero probar marzo 2026*\n"
            "· *¿Por qué 5 minutos?*\n"
            "· *¿Puedo crear una estrategia nueva?*"
        ),
        actions=[
            ChatAction(type="navigate", label="Simulador WS", href="/fondeo/liquidity-sweep"),
        ],
    )


@router.post("/chat", response_model=ChatResponse)
def assistant_chat(req: ChatRequest) -> dict[str, Any]:
    return _reply_for(req.message).model_dump()
