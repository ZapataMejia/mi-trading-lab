"""Entry ASGI para VPS NeuraVPS (uvicorn). Sin límite estricto de RAM como PA free."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)

os.environ.setdefault(
    "ALLOWED_ORIGINS",
    "https://frontend-kappa-sepia-16.vercel.app,http://localhost:3000",
)
# Modo VPS: sin restricciones de nube barata
os.environ.setdefault("ONLINE_MODE", "0")
os.environ.setdefault("ENABLE_CRYPTO_BACKTEST", "0")
# 730 días ≈ 2 años por simulación (frontend + backend)
os.environ.setdefault("MAX_LIQ_SIM_DAYS", "730")
os.environ.setdefault("MAX_FONDEO_SIM_DAYS", "730")

from webapp.backend.main import app  # noqa: E402,F401
