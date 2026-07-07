# Estrategia para pasar eval WS $5k — conclusiones del lab

> Investigación: lab (391k barras EURUSD M5), búsqueda web prop firms, reglas WS + curso HobbyCode.

---

## Lo que encontramos (datos reales)

### Hedge 2 cuentas (curso)
| Métrica | Resultado |
|---------|-----------|
| Ventanas 7–60 días | **0%** pass rate (todas las configs) |
| Config curso 9/20 8–10 | 0% |
| Comisiones + cierre sesión | Ambas cuentas pierden poco a poco; no divergen a +8%/-8% en histórico |

**Internet / industria:** hedge en 2 cuentas de la misma prop firm está **prohibido y detectado** (timing, tamaño, instrumento opuesto). WS permite varias evals pero no garantiza tolerancia al espejo.

**Conclusión hedge:** el curso puede funcionar en vivo con copiador + guardián +8%, pero **el lab no lo valida**. Riesgo de breach por detección WS.

### EMA single (misma lógica Fondeo, 1 cuenta)
| Config | Pasa eval 5 años | Ventana 14d | Ventana 90d | Pasa en ≤180d |
|--------|------------------|-------------|-------------|---------------|
| **9/18, 7–11, off+7** | ✅ +$1,175 | 0% | 0% | **3.7%** (1/27), med **160d** |
| 9/20, 8–10 (curso) | ✅ +$571 | 0% | 0% | 0% |
| 3/8 TP2.5 | ✅ +$2,022 | 0% | 0% | 0% (muy lento) |

**Mejor config del lab:** EMA **9/18**, sesión **07:00–11:00**, TP **1:1**, riesgo **2.1%**, offset **+7**.

### London breakout (alternativa web)
Probar en lab → **-69% DD**, demasiados trades. Descartada en EURUSD M5.

---

## Qué haría yo con 2 cuentas regaladas

### Plan recomendado (realista + reglas WS)

```
CUENTA 1 (activa)     → EMA 9/18 single, robot LONG+SHORT
CUENTA 2 (reserva)    → NO hedge espejo; activar solo si cuenta 1 hace breach
```

| Paso | Acción |
|------|--------|
| 1 | VPS + SQX con **9/18, 7–11, 2.1%, max 2/d, offset +7** |
| 2 | **Demo 2 semanas** en cuenta 1: ¿trades en sesión? ¿DD < 5%/día? |
| 3 | Si OK → eval cuenta 1. Plazo mental: **2–5 meses** (WS sin límite de tiempo) |
| 4 | Si cuenta 1 breach → activar cuenta 2 con misma config |

### Si insistís en hedge (curso)

| Paso | Acción |
|------|--------|
| 1 | Cuentas a **nombres distintos** (tú + hermana) |
| 2 | Copiador **inverso** + guardián **+8% equity** |
| 3 | **Demo 10 días**: ¿A y B van opuestas? ¿Una sube otras baja? |
| 4 | Si no hay divergencia en 10d → **parar** y cambiar a single 9/18 |
| 5 | Asumir riesgo detección WS |

---

## Parámetros SQX / lab (ganador)

```
Par:           EURUSD M5
EMA:           9 / 18
Risk:          2.1%
TP ratio:      1.0
Sesión:        07:00 – 11:00 (hora broker)
Max trades/d:  2
Offset SQX:    +7 (EST+07)
Capital:       $5,000
```

Validar en SQX: ~**46 trades**, PnL **~+$1,000–1,200**, DD eval **< 8%** (2017–2022).

---

## Validación (3 fases)

1. **Lab** — `python3 scripts/eval_time_to_pass.py` + botón “Backtest hedge completo” en /fondeo  
2. **Demo VPS 2 semanas** — checklist en `sqx/VALIDAR_HEDGE.md`  
3. **Eval live** — meta +8%, mín. 4 días trading, SL < 2 min  

---

## Scripts útiles

```bash
python3 scripts/eval_time_to_pass.py    # % pass en 180 días
python3 scripts/hedge_lab_run.py          # reporte hedge
python3 scripts/eval_master_hunt.py       # búsqueda amplia
```

Reportes: `data/forex_cache/eval_time_to_pass.json`, `hedge_lab_report.json`

---

## Respuesta directa

| Pregunta | Respuesta |
|----------|-----------|
| ¿Hay estrategia que pase en semanas en backtest? | **No** en nuestros datos |
| ¿Hay estrategia que pase eval WS (sin plazo)? | **Sí: EMA 9/18** |
| ¿Hedge del curso en backtest? | **No validado** |
| ¿Qué usar? | **9/18 single** + cuenta 2 de reserva; hedge solo si demo muestra divergencia |
