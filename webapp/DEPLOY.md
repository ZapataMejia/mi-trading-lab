# Desplegar Mi Trading Lab (hermana en remoto)

## Estado actual (ZapataMejia)

| Parte | URL / repo |
|-------|------------|
| **GitHub** | https://github.com/ZapataMejia/mi-trading-lab (privado) |
| **Frontend (Vercel)** | https://frontend-kappa-sepia-16.vercel.app |
| **Backend (Render)** | Pendiente — ver paso 1 abajo |

---

## 1. Backend en Render (5 minutos, una sola vez)

1. Abre: https://render.com/deploy?repo=https://github.com/ZapataMejia/mi-trading-lab  
2. Inicia sesión con **GitHub → ZapataMejia** (autoriza el repo privado).
3. Render detecta `render.yaml` y crea el servicio `mi-trading-lab-api`.
4. En **Environment** del servicio, añade:
   - `ALLOWED_ORIGINS` = `https://frontend-kappa-sepia-16.vercel.app`
5. Espera el deploy (~5–10 min). Copia la URL, p. ej. `https://mi-trading-lab-api.onrender.com`.
6. Comprueba: `https://TU-URL.onrender.com/api/health` → `{"status":"ok"}`.

El CSV EURUSD (22 MB, 2022–2026) ya va en el repo como `EURUSD_M5_deploy.csv`; el build lo copia a `EURUSD_M5.csv`.

---

## 2. Conectar frontend al backend

En [Vercel → frontend → Settings → Environment Variables](https://vercel.com/zapatamejias-projects/frontend/settings/environment-variables):

- `NEXT_PUBLIC_API_BASE` = `https://TU-URL.onrender.com` (sin barra final)
- Redeploy **Production**.

O desde terminal (sustituye la URL de Render):

```bash
cd webapp/frontend
printf 'https://mi-trading-lab-api.onrender.com' | npx vercel env rm NEXT_PUBLIC_API_BASE production -y
printf 'https://mi-trading-lab-api.onrender.com' | npx vercel env add NEXT_PUBLIC_API_BASE production
npx vercel deploy --prod
```

---

## 3. Probar con tu hermana

- Simulador: https://frontend-kappa-sepia-16.vercel.app/fondeo/liquidity-sweep  
- Asistente: https://frontend-kappa-sepia-16.vercel.app/asistente  
- Preset gráfico Mar 2026: `?preset=q1-2026`

---

## Local (desarrollo)

```bash
webapp/start_lab.command
# Frontend http://localhost:3000 · Backend http://localhost:8000
```

---

## Notas

- **Render free** duerme tras ~15 min sin uso; la primera petición tarda ~30 s.
- El asistente **no usa Cursor**; solo FAQ del lab.
- SQX sigue siendo local; el lab web es el motor Python.
