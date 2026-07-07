"""Entry ASGI para PythonAnywhere (uvicorn)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)

os.environ.setdefault(
    "ALLOWED_ORIGINS",
    "https://frontend-kappa-sepia-16.vercel.app,http://localhost:3000",
)
os.environ.setdefault("ONLINE_MODE", "1")
os.environ.setdefault("ENABLE_CRYPTO_BACKTEST", "0")
os.environ.setdefault("MAX_LIQ_SIM_DAYS", "90")
os.environ.setdefault("MAX_FONDEO_SIM_DAYS", "90")

from webapp.backend.main import app  # noqa: E402,F401
