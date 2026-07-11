#!/usr/bin/env python3
"""Sube archivos del backend a PythonAnywhere y recarga la web app."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
USER = os.environ.get("PA_USER", "mitradinglab")
DOMAIN = os.environ.get("PA_DOMAIN", f"{USER}.pythonanywhere.com")
TOKEN = os.environ.get("PYTHONANYWHERE_API_TOKEN") or os.environ.get("PA_API_TOKEN")

FILES = [
    ROOT / "webapp/backend/api/fondeo_api.py",
    ROOT / "webapp/backend/markets/forex.py",
    ROOT / "webapp/backend/engine/indicators.py",
    ROOT / "webapp/backend/engine/liquidity_sweep_engine.py",
    ROOT / "webapp/backend/main.py",
    ROOT / "webapp/backend/pa_main.py",
]


def upload_file(local: Path) -> None:
    rel = local.relative_to(ROOT).as_posix()
    remote = f"/home/{USER}/mi-trading-lab/{rel}"
    url = f"https://www.pythonanywhere.com/api/v0/user/{USER}/files/path{remote}"
    content = local.read_bytes()
    resp = requests.post(
        url,
        files={"content": (local.name, content, "text/plain")},
        headers={"Authorization": f"Token {TOKEN}"},
        timeout=120,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Upload {rel}: HTTP {resp.status_code} {resp.text[:300]}")
    print(f"  OK {rel}")


def reload_webapp() -> None:
    # v0 a veces devuelve 403/500; v1 funciona en cuentas nuevas de PA.
    candidates = [
        ("v1", f"https://www.pythonanywhere.com/api/v1/user/{USER}/websites/{DOMAIN}/reload/"),
        ("v0", f"https://www.pythonanywhere.com/api/v0/user/{USER}/webapps/{DOMAIN}/reload/"),
        ("v0-www", f"https://www.pythonanywhere.com/api/v0/user/{USER}/webapps/www.{DOMAIN}/reload/"),
    ]
    last_err = ""
    for label, url in candidates:
        resp = requests.post(url, headers={"Authorization": f"Token {TOKEN}"}, timeout=60)
        if resp.status_code == 200:
            print(f"  Reload OK ({label})")
            return
        last_err = f"{label}: HTTP {resp.status_code} {resp.text[:120]}"
    print(f"  Aviso: reload API falló ({last_err}). Usa Web → Reload en el dashboard de PA.")


def health_check() -> None:
    url = f"https://{DOMAIN}/api/health"
    for attempt in range(8):
        try:
            resp = requests.get(url, timeout=20)
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                print(f"  Health OK: {url}")
                return
        except Exception:
            pass
        import time

        time.sleep(5)
    print(f"  Aviso: health aún no responde en {url} — espera 30 s y prueba manualmente")


def main() -> int:
    if not TOKEN:
        print("Falta PYTHONANYWHERE_API_TOKEN (Account → API token en PA)", file=sys.stderr)
        return 1
    missing = [p for p in FILES if not p.is_file()]
    if missing:
        print("Archivos no encontrados:", ", ".join(str(p) for p in missing), file=sys.stderr)
        return 1

    print(f"Subiendo backend a {USER}…")
    for path in FILES:
        upload_file(path)
    print("Recargando web app…")
    reload_webapp()
    print("Comprobando salud…")
    health_check()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
