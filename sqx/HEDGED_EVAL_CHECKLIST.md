# Evaluación WS Funded $5k — método hedged (curso HobbyCode)

> Basado en transcripciones del curso (`mentoria_2.txt`) + reglas oficiales WS CLASSIC.
> Este método es el que el mentor usa para pasar en **3–7 días**, no la EMA simple sola.

## Reglas WS CLASSIC $5k (oficial)

| Regla | Valor |
|-------|--------|
| Fase 1 meta | +8% ($400) |
| Fase 2 meta | +5% ($250) |
| Plazo máximo | **Sin límite** |
| Inactividad | 30 días sin operar → breach |
| Días mínimos trading | **4 días** |
| DD diario | 5% ($250) |
| DD máximo estático | 8% ($400) |
| Riesgo por trading idea | ≤50% DD diario → **2,5% máx.** (curso: **2,1%**) |
| SL | Obligatorio en 2 minutos |
| EAs | Permitidos en eval CLASSIC |

Fuentes: [WS FAQ](https://wsfunded.com/en/faq/) · [Classic 2 fases](https://faq.wsfunded.com/en/articles/8717270-2-phases-wall-street-classic)

---

## Por qué 2 cuentas (hedge)

1. Comprás **2 evaluaciones CLASSIC $5k** en WS Funded (~$59 c/u).
2. **Cuenta A** → robot abre **LONG** en cruce EMA.
3. **Cuenta B** → robot abre **SHORT** en el mismo cruce (copiador inverso o segundo EA).
4. Una cuenta pierde, la otra gana **aprox. lo mismo** → avanzás hacia +8% en la ganadora sin depender de dirección.
5. Objetivo mentor: **+8% en 3–7 días** (no meses).

---

## Parámetros estrategia EMA (curso → SQX)

| Parámetro | Valor curso |
|-----------|-------------|
| Par | EURUSD |
| Temporalidad | M5 |
| EMA rápida / lenta | 9 / 20 (baseline) |
| Risk % | **2,1%** (tope WS por idea) |
| TP ratio | 1.0 (ajustar en lab) |
| Sesión broker | **08:00 – 10:00** |
| Max trades / día | **2** |
| Offset timezone | **EST+07** en SQX |
| Capital | $5,000 |

---

## Checklist VPS — AlgoWizard (cuenta A, LONG)

- [ ] Datos: EURUSD M5 Dukascopy (mismo CSV que lab)
- [ ] Snippets `FondeoEMAcross` instalados (`sqx/bundle/LEEME.txt`)
- [ ] AlgoWizard → Fondeo Long Entry + Short Entry
- [ ] MM: Risk fixed **2,1%**
- [ ] SL/TP: FondeoEMAcross (Shift **0**)
- [ ] Backtest 2017–2022 → comparar trades/PnL con lab
- [ ] Guardar `FondeoEMA.sqx`

## Checklist VPS — Cuenta B (SHORT / hedge)

- [ ] Segunda eval WS a nombre distinto (ej. familiar) si es posible
- [ ] Mismo VPS, **pestaña MT5 separada**
- [ ] Copiador o EA espejo → operaciones **inversas** a cuenta A
- [ ] Mismo lotaje / multiplicador si tamaños de cuenta difieren
- [ ] Límite equity en EA: cerrar todo al **+8,05%** (meta fase 1)
- [ ] Límite pérdida diaria: **~4,5%** (margen sobre 2,1% × 2 trades)

## Checklist eval en vivo

- [ ] **Mínimo 4 días** con al menos 1 trade (regla WS)
- [ ] No superar **5% DD diario** ($250)
- [ ] No bajar de **$4,600** (DD estático 8%)
- [ ] SL en cada trade en **< 2 min**
- [ ] Operar dentro sesión 8–10 (broker)
- [ ] Máx **2 trades/día** por cuenta
- [ ] Meta fase 1: **+$400** → cerrar / bloquear robot

## Checklist después de fase 1

- [ ] Repetir fase 2 con meta **+5%** ($250)
- [ ] Mismo setup hedged o estrategia validada
- [ ] Export MT5 + parche HobbyCode cuando params confirmados

---

## Lo que el lab local NO simula bien

- Cierre de sesión 8–10 con TP lejano → en histórico rara vez llega +8% en días (el curso usa copiador en vivo que para en +8% equity aunque el trade siga abierto)
- Comisiones/spread reales del broker WS
- Usar botón **“Probar hedge 2 cuentas”** en http://localhost:3000/fondeo

---

## Lab local — probar hedge

1. `./webapp/start_lab.command` → http://localhost:3000/fondeo
2. Parámetros curso: EMA 9/20, 2.1%, sesión 8–10, offset +7
3. Clic **Probar hedge 2 cuentas** → ves Cuenta A vs B y % ventanas 7/14/30 días

---

## Siguiente paso recomendado

1. Probar hedge en lab (botón arriba)
2. Validar en SQX/VPS con 2 MT5 (este doc)
3. Activar las 2 evals regaladas como par A/B
