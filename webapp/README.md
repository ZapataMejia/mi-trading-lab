# Mi Trading Lab

App local para descubrir, backtestear y comparar estrategias de trading.
Soporta Polymarket (hoy) y va a soportar crypto perp y options (próximos sprints).

## Arquitectura

```
webapp/
├── backend/                ← FastAPI (Python) — puerto 8000
│   ├── api/                ← endpoints HTTP
│   ├── engine/             ← motor de backtest + métricas
│   ├── markets/            ← adapters por tipo de mercado
│   └── main.py             ← punto de entrada
├── frontend/               ← Next.js 16 + Tailwind v4 — puerto 3000
│   └── src/
│       ├── app/            ← rutas (App Router)
│       ├── components/     ← UI components
│       └── lib/            ← cliente API + tipos
└── start_lab.command       ← doble click para arrancar todo

strategies/                 ← (al lado del repo) las estrategias en sí
├── base.py                 ← clases base
├── polymarket/             ← 5 estrategias listas
└── _examples/              ← templates
```

## Primer arranque

### 1. Backend (una sola vez)

```bash
cd /Users/santiago/Documents/Personal/trading
source .venv/bin/activate
pip install fastapi "uvicorn[standard]" pydantic
```

### 2. Frontend (una sola vez)

```bash
cd webapp/frontend
npm install
```

### 3. Levantar todo

```bash
./webapp/start_lab.command
```

(Doble click desde Finder también funciona, después de `chmod +x`.)

Abre automáticamente el navegador en http://localhost:3000.

## Uso diario

1. Doble click en `start_lab.command`
2. La web se abre sola en http://localhost:3000
3. Click en cualquier estrategia → "Correr backtest" → ver resultados
4. Para cerrar: cierra la ventana de Terminal que se abrió

## Crear una nueva estrategia

Lo más rápido es decírselo a Claude en Cursor:

> "Hagamos una estrategia que opere solo SOL los viernes con edge >25pp"

Claude te crea el archivo en `strategies/polymarket/` y agrega el import en
el `__init__.py`. Después en la web app, click "Recargar" y aparece.

Alternativamente: copiá `strategies/_examples/template_polymarket.py` y editalo.

## API

El backend expone:

| Método | Endpoint | Qué hace |
|---|---|---|
| GET | `/` | Health + count de estrategias |
| GET | `/api/health` | Healthcheck simple |
| GET | `/api/strategies` | Lista todas las estrategias |
| GET | `/api/strategies/{id}` | Detalle de una |
| POST | `/api/strategies/reload` | Re-descubre estrategias (después de crear una nueva) |
| POST | `/api/backtest/run` | Corre un backtest |
| GET | `/api/backtest/data-info` | Metadata de datasets disponibles |

Documentación OpenAPI interactiva: http://localhost:8000/docs

## Datasets disponibles

| Key | Origen | Rango | Mercados |
|---|---|---|---|
| `hourly_full` | Backtest con modelo log-normal | jun 2025 → jun 2027 | ~30k |
| `v4_real` | CLOB minuto-a-minuto (real) | jun 2025 → may 2026 | ~30k |

## Troubleshooting

**"Port 8000 already in use"** → el script libera puertos automáticamente, pero si querés a mano:
```bash
lsof -ti :8000 | xargs kill -9
lsof -ti :3000 | xargs kill -9
```

**Backend no arranca** → revisá `webapp/logs/backend.log`

**Frontend no carga** → revisá `webapp/logs/frontend.log`

**El backend dice "0 strategies"** → revisá imports en `strategies/polymarket/__init__.py`
