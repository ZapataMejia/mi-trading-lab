"""WSGI entry for PythonAnywhere (FastAPI via a2wsgi)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from a2wsgi import ASGIMiddleware
from webapp.backend.main import app

application = ASGIMiddleware(app)
