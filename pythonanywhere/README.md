# Backend en PythonAnywhere (gratis, sin tarjeta)

## 1. Cuenta
- https://www.pythonanywhere.com/registration/register/beginner/ → registro free

## 2. Subir código
En **Files** → `/home/TU_USUARIO/`:
- Opción A: `git clone` del repo (si es público o con token)
- Opción B: subir zip del proyecto

Estructura esperada:
```
/home/TU_USUARIO/mi-trading-lab/
  webapp/backend/...
  strategies/...
  data/forex_cache/EURUSD_M5_deploy.csv
  data/forex_cache/EURUSD_M5_full.csv.gz
  pythonanywhere/wsgi.py
  requirements-pa.txt
```

Instalar datos forex (histórico completo 2003→hoy, ~26 MB comprimido):
```bash
cd ~/mi-trading-lab
python3 scripts/install_forex_data.py
```
Si solo existe `EURUSD_M5_deploy.csv`, usa el subset 2022–2026. Si existe `EURUSD_M5_full.csv.gz`, extrae el histórico completo.

Subir desde tu Mac (SSH configurado en PA):
```bash
./scripts/upload_pa_forex_full.sh
```

Copia manual del subset (fallback):
```bash
cp data/forex_cache/EURUSD_M5_deploy.csv data/forex_cache/EURUSD_M5.csv
```

## 3. Virtualenv + deps
```bash
mkvirtualenv --python=/usr/bin/python3.10 mi-trading-lab
cd ~/mi-trading-lab
pip install -r requirements-pa.txt
```

## 4. Web app
**Web** → **Add a new web app** → Manual config → Python 3.10

**WSGI file** (`/var/www/TU_USUARIO_pythonanywhere_com_wsgi.py`):
```python
import sys
sys.path.insert(0, '/home/TU_USUARIO/mi-trading-lab')
from pythonanywhere.wsgi import application
```

**Virtualenv:** `/home/TU_USUARIO/.virtualenvs/mi-trading-lab`

**Environment variables** (Web → Environment):
```
ALLOWED_ORIGINS=https://frontend-kappa-sepia-16.vercel.app
ENABLE_CRYPTO_BACKTEST=0
ONLINE_MODE=1
MAX_LIQ_SIM_DAYS=90
MAX_FONDEO_SIM_DAYS=90
```

> **RAM (3 GB en cuenta free):** no lances simulaciones de años enteros en una sola petición.
> El frontend ya limita a 90 días; si el servidor responde 429, espera a que termine la simulación anterior.

**Reload** web app.

## 5. Probar
`https://TU_USUARIO.pythonanywhere.com/api/health` → `{"status":"ok"}`

## 6. Vercel
Variable `NEXT_PUBLIC_API_BASE` = `https://TU_USUARIO.pythonanywhere.com`
