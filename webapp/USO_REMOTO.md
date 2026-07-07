# Mi Trading Lab — hermana en otro país (gratis, sin tarjeta)

Tu hermana **no puede** usar la IP de WiFi (`192.168.x.x`). Necesitas un túnel privado gratis.

**Recomendado: Tailscale** — VPN personal, plan free, **no pide tarjeta**.

---

## Paso 1 — Tú (una sola vez)

1. Instala Tailscale en tu Mac: https://tailscale.com/download/mac  
   (o `brew install tailscale` y abre la app)
2. Inicia sesión (Google/GitHub/email).
3. En la app Tailscale → **Invite user** → email de tu hermana.
4. Ella acepta la invitación e instala Tailscale en su celular/PC (mismo link).

---

## Paso 2 — Arrancar el lab

Doble click en **`webapp/start_lab.command`**.

Si Tailscale está activo, la Terminal muestra:

```
Hermana (otro país, Tailscale):
  http://100.x.x.x:3000/fondeo/liquidity-sweep
```

Copia ese link y envíaselo por WhatsApp.

---

## Paso 3 — Ella

1. Tailscale **encendido** en su dispositivo (icono verde).
2. Abre el link que le mandaste en Chrome/Safari.
3. Listo — simulador, asistente y gráficos.

| Página | Sufijo |
|--------|--------|
| Simulador | `/fondeo/liquidity-sweep` |
| Asistente | `/asistente` |
| Mar 2026 + gráfico | `/fondeo/liquidity-sweep?preset=q1-2026` |

---

## Requisitos

- Tu Mac **encendida** con el lab abierto (`start_lab.command`).
- Tailscale **activo** en tu Mac y en el dispositivo de ella.
- **$0** — plan personal de Tailscale no cobra.

---

## Si no ves link de Tailscale al arrancar

```bash
# ¿Tailscale instalado y conectado?
tailscale status
tailscale ip -4
```

Si no está instalado → https://tailscale.com/download

---

## Alternativa (menos estable, sin cuenta)

Cloudflare quick tunnel — URL cambia cada vez, no recomendado para uso frecuente.

---

## Lo que NO hace falta

- Render / Vercel backend / tarjeta de crédito
- Misma WiFi
- SQX en la nube (el lab web es el simulador Python)
