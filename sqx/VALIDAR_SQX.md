# Validar en SQX — Config ganadora (lab local)

Config que **pasa eval WS CLASSIC $5k fase 1** en el lab (datos SQX 2017–2022).

## Parámetros exactos (AlgoWizard)

| Parámetro | Valor |
|-----------|-------|
| Símbolo | EURUSD |
| Timeframe | M5 |
| Capital | 5000 |
| EMA rápida | **9** |
| EMA lenta | **18** |
| Risk % | **2.1** |
| TP ratio | **1.0** |
| Sesión inicio | **700** (07:00 hora broker) |
| Sesión fin | **1100** (11:00 hora broker) |
| Max trades/día | **2** |
| Money Management | Risk fixed % → **2.1%** |
| Long + Short | ambos activos |

### Timezone (crítico)

En el lab usamos **offset UTC → broker +7** (≈ EST+07 de SQX).

Si los resultados no cuadran:
1. Probar sesión **700–1100** con datos en hora broker +7
2. Anotar qué timezone muestra SQX en el chart (EST+07, etc.)
3. Objetivo: **~46 trades** y PnL **~+$1,000–1,200** en 2017-01-03 → 2022-03-31

---

## Referencia lab (Mac) — comparar con SQX

| Métrica | Lab local |
|---------|-----------|
| Trades | ~46 |
| PnL | ~+$1,175 |
| Max DD (eval WS) | ~-2.4% |
| Max DD (equity curve) | ~-10% — SQX puede mostrar este; lo que importa es DD eval < 8% |
| Profit Factor | ~1.60 |
| Win rate | ~60% |

**Aceptable si SQX está cerca:** ±10 trades, PnL mismo signo y orden de magnitud, DD < 8%.

---

## Pasos en el VPS

### 1. Snippets (si no están instalados)

Ver `sqx/bundle/LEEME.txt` — copiar `user/` a `C:\StrategyQuant X\user\` → Compile all.

### 2. AlgoWizard — estrategia

1. Nueva estrategia
2. **Long entry:** condición `Fondeo Long Entry` → Enter at Market  
   SL: `FondeoEMAcross → LongStop` · TP: `LongTP`
3. **Short entry:** condición `Fondeo Short Entry` → Enter at Market  
   SL: `ShortStop` · TP: `ShortTP`
4. Poner **los mismos parámetros** en el indicador y en las condiciones (9/18, 2.1%, TP 1.0, sesión, max 2/d)
5. MM: **Risk fixed 2.1%**

### 3. Datos de backtest

- **Mismo CSV** que en el Mac: `EURUSD_M5` export Dukascopy/SQX
- Rango: **2017-01-03 → 2022-03-31**
- No uses otro dataset distinto al del lab

### 4. Correr y anotar

```
Trades: ___
PnL: $___
Max DD: ___%
PF: ___
```

### 5. Guardar

`File → Save as → FondeoEMA_v2.sqx`

### 6. Si cuadra → export MT5

Seguir curso HobbyCode: export MT5 + parche WS.

---

## Checklist eval WS (fase 1)

- [ ] Meta +8% ($400) en backtest SQX
- [ ] Max DD estático < 8%
- [ ] DD diario < 5%
- [ ] Al menos 4 días con trades en el periodo
- [ ] Risk 2.1% por trade
- [ ] SL en cada operación (Shift 0 en SL/TP — **no Shift 1**)

---

## Si no cuadra

| Síntoma | Ajuste |
|---------|--------|
| Muchos más/menos trades | Timezone / sesión 700–1100 vs 800–1100 |
| DD muy distinto | Mismo CSV y rango de fechas |
| PnL opuesto | Offset horario |
| 48 vs 46 trades (referencia vieja) | Normal — buscar DD < 8% y PnL positivo |

---

## Después de SQX

1. Export MT5 + parche HobbyCode
2. Cuenta demo WS CLASSIC $5k
3. EA en eval (permitido en CLASSIC, no en Instant)
4. Límites MT5: meta +8.05%, DD diario 5%, DD total 8% (modo fondeo del curso)

Lab local: http://localhost:3000/fondeo (defaults ya cargados)
