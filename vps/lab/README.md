# Mi Trading Lab — API en VPS grande (para tu hermana)

Objetivo: **misma URL de Vercel** para ella, pero el motor corre en tu **VPS grande (20 GB RAM)** → backtests de **hasta ~2 años en un clic**.

```
Hermana → https://frontend-kappa-sepia-16.vercel.app  (igual que ahora)
              ↓
         Tu VPS (HTTPS) → uvicorn puerto 8000
```

---

## Antes de empezar (en tu Mac)

1. Sube estos cambios a GitHub (`mi-trading-lab`) o prepárate a copiar la carpeta por RDP.
2. Ten a mano acceso **RDP** al **VPS grande** (StrategyQuant), no al pequeño de Polymarket.
3. Necesitas una **URL HTTPS fija** para el API. Opciones:
   - **A) Cloudflare Tunnel + subdominio** (recomendado) — ej. `https://lab-api.tudominio.com`
   - **B) Tailscale Funnel** — si ya usas Tailscale en el VPS: `https://xxx.tailnet.ts.net`

Sin HTTPS el navegador **no** dejará a Vercel llamar al API.

---

## PASO 1 — Conectar al VPS grande

1. Abre **Escritorio remoto** (RDP) al VPS grande de NeuraVPS.
2. Abre **PowerShell** (como Administrador está bien).

---

## PASO 2 — Instalar Git y Python (si no están)

```powershell
python --version
git --version
```

Si falta algo:

```powershell
winget install --id Python.Python.3.12 -e
winget install --id Git.Git -e
```

Cierra y reabre PowerShell después.

---

## PASO 3 — Clonar el proyecto

```powershell
cd $HOME
git clone https://github.com/ZapataMejia/mi-trading-lab.git
cd mi-trading-lab
```

Si el repo es privado y falla el clone: hazlo público 2 minutos (como con polymarket-bot) o usa token de GitHub.

**Alternativa sin Git:** comprime la carpeta `trading` en tu Mac, súbela por RDP a `C:\Users\Administrador\mi-trading-lab`.

---

## PASO 4 — Setup del lab (una sola vez)

```powershell
cd $HOME\mi-trading-lab
powershell -ExecutionPolicy Bypass -File vps\lab\setup_lab.ps1
```

---

## PASO 5 — Datos EURUSD (histórico)

**Opción fácil — copiar desde tu Mac por RDP:**

1. En tu Mac, archivo: `data/forex_cache/EURUSD_M5_full.csv.gz` (~25 MB)
2. Arrástralo al VPS → `C:\Users\Administrador\mi-trading-lab\data\forex_cache\`
3. En el VPS:

```powershell
cd $HOME\mi-trading-lab
.\.venv-lab\Scripts\python.exe scripts\install_forex_data.py
```

**Opción SQX:** ya tienes Dukascopy en el VPS — exporta EURUSD M5 CSV a esa misma carpeta y renómbralo `EURUSD_M5.csv`.

Comprobar:

```powershell
curl http://127.0.0.1:8000/api/fondeo/data-range?symbol=EURUSD&timeframe=M5
```

(Si el API aún no corre, salta al paso 6 y vuelve aquí.)

---

## PASO 6 — Arrancar el API

En una ventana PowerShell (déjala abierta):

```powershell
cd $HOME\mi-trading-lab
powershell -ExecutionPolicy Bypass -File vps\lab\start_lab_api.ps1
```

En **otra** ventana, prueba:

```powershell
curl http://127.0.0.1:8000/api/health
```

Debe responder: `{"status":"ok"}`

Para que arranque solo al encender el VPS (opcional):

```powershell
powershell -ExecutionPolicy Bypass -File vps\lab\install_lab_autostart.ps1
```

---

## PASO 7 — HTTPS público (Cloudflare Tunnel)

### 7.1 Instalar cloudflared

```powershell
winget install --id Cloudflare.cloudflared -e
```

Cierra y reabre PowerShell.

### 7.2 Login y crear túnel

```powershell
cloudflared tunnel login
```

Se abre el navegador → elige tu dominio en Cloudflare.

```powershell
cloudflared tunnel create mi-trading-lab
```

Anota el **Tunnel ID** que imprime.

### 7.3 DNS

Sustituye `lab-api.tudominio.com` por tu subdominio real:

```powershell
cloudflared tunnel route dns mi-trading-lab lab-api.tudominio.com
```

### 7.4 Config

Crea el archivo (sustituye `TU_USUARIO` y `TUNNEL_ID`):

`C:\Users\Administrador\.cloudflared\config.yml`

Copia desde `vps\lab\cloudflared-config.example.yml` y edita.

### 7.5 Correr el túnel

Con el API ya corriendo en puerto 8000:

```powershell
cloudflared tunnel run mi-trading-lab
```

Prueba desde tu Mac:

```bash
curl https://lab-api.tudominio.com/api/health
```

Debe decir `{"status":"ok"}`.

> **Sin dominio propio:** Cloudflare Tunnel necesita un dominio en tu cuenta. Si no tienes, usa Tailscale Funnel (paso 7B abajo) o registra un dominio barato (~$10/año).

### 7B — Alternativa: Tailscale Funnel

Si el VPS tiene Tailscale:

```powershell
tailscale funnel 8000
```

Te da una URL `https://....ts.net` — úsala como API base en Vercel.

---

## PASO 8 — Conectar Vercel (desde tu Mac)

Sustituye la URL por la tuya (`https://lab-api.tudominio.com`):

```bash
cd webapp/frontend
printf 'https://lab-api.tudominio.com' | npx vercel env rm NEXT_PUBLIC_API_BASE production -y 2>/dev/null || true
printf 'https://lab-api.tudominio.com' | npx vercel env add NEXT_PUBLIC_API_BASE production
npx vercel deploy --prod
```

---

## PASO 9 — Probar como tu hermana

1. Abre: https://frontend-kappa-sepia-16.vercel.app/fondeo/liquidity-sweep
2. Fechas: **01/01/2025 → 31/12/2025** (365 días)
3. Pulsa **Simular este periodo** — debe funcionar (tarda 1–3 min)
4. Arriba debería decir **hasta 730 días** por simulación, no 90

**El link de WhatsApp para ella no cambia.**

---

## Resumen de ventanas en el VPS

| Ventana | Qué corre |
|---------|-----------|
| 1 | `start_lab_api.ps1` → API puerto 8000 |
| 2 | `cloudflared tunnel run mi-trading-lab` → HTTPS público |
| (opcional) | StrategyQuant — no cerrar si lo usas |

---

## Si algo falla

| Síntoma | Qué hacer |
|---------|-----------|
| `curl localhost:8000` falla | Revisa que `start_lab_api.ps1` siga corriendo |
| Vercel no conecta | CORS: `ALLOWED_ORIGINS` debe incluir la URL de Vercel |
| Sigue límite 90 días | Vercel aún apunta a PythonAnywhere — repite paso 8 |
| Sin datos forex | Repite paso 5 |
| Simulación muy lenta | Normal en 365 días; el VPS grande aguanta |

---

## Volver a PythonAnywhere

En Vercel:

```bash
printf 'https://mitradinglab.pythonanywhere.com' | npx vercel env add NEXT_PUBLIC_API_BASE production
npx vercel deploy --prod
```
