# Mi Trading Lab — uso local (gratis)

Todo corre **en la Mac de Santiago**. No hay suscripciones ni tarjetas.

## Arrancar (Santiago)

1. Doble click en **`webapp/start_lab.command`**
2. Se abre el simulador Liquidity Sweep en el navegador
3. **No cierres** la ventana negra de Terminal mientras tu hermana use el lab

Primera vez solamente:

```bash
cd /Users/santiago/Documents/Personal/trading
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd webapp/frontend && npm install
```

## Tu hermana (misma casa, misma WiFi)

Cuando arranques el lab, la Terminal muestra algo como:

```
Hermana (misma WiFi): http://192.168.1.53:3000/fondeo/liquidity-sweep
```

Envíale ese enlace por WhatsApp. Ella lo abre en celular o laptop.

| Qué | Ruta |
|-----|------|
| Simulador WS | `/fondeo/liquidity-sweep` |
| Asistente (preguntas) | `/asistente` |
| Lab Forex | `/lab?mercado=forex` |

Preset recomendado para gráfico Mar 2026:  
`/fondeo/liquidity-sweep?preset=q1-2026`

## Limitaciones

- **Solo funciona mientras tu Mac esté encendida** y el lab abierto
- **Misma WiFi** — no sirve desde otra ciudad sin túnel extra
- El asistente **no crea estrategias nuevas** (solo ayuda a probar)

## Apagar

Cierra la ventana de Terminal del lab (o Ctrl+C).

## Si algo falla

```bash
lsof -ti :8000 | xargs kill -9
lsof -ti :3000 | xargs kill -9
```

Luego vuelve a abrir `start_lab.command`.

Logs: `webapp/logs/backend.log` y `webapp/logs/frontend.log`
