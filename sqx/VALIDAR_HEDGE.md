# Cómo validar el hedge antes de ir a live

Tres fases. Cada una responde una pregunta distinta.

---

## Fase 1 — Backtest histórico (lab, 1–2 horas)

**Pregunta:** ¿En el pasado, algún par A/B hubiera pasado eval en ~1–2 semanas?

**Dónde:** http://localhost:3000/fondeo → **Probar hedge 2 cuentas**

**Cómo:**
1. Parámetros curso: EMA 9/20, 2.1%, sesión 8–10, offset +7
2. Fechas acotadas a **30–60 días** (simula 1 eval, no años)
3. Mirar:
   - **Ventanas 7d / 14d / 30d** → % donde el par “gana”
   - Cuenta A vs B (una debería ir hacia +8%, otra hacia -8%)

**Criterio mínimo (orientativo):**
- ≥ **30%** ventanas 14d con 1 ganadora → seguir a fase 2
- **0%** en 14d y 30d → ajustar params o revisar offset/sesión antes de demo

**Qué modela el lab (v2):**
- Par espejo A/B ✓
- Cierre sesión 8–10 ✓
- **Guardián +8% equity** (incluye flotante, como copiador curso) ✓
- Comisión ~$5/trade/cuenta ✓

**Qué NO modela:** spread exacto WS, latencia, rechazo de orden, reglas prop firm sobre hedge.

---

## Fase 2 — Demo en vivo (1–2 semanas)

**Pregunta:** ¿Con datos reales **ahora**, el par se comporta como esperamos?

**Opción A (recomendada):** Las 2 evals regaladas **ya son demo** ($5k simulados WS). No arriesgáis dinero propio.

**Opción B:** 2 cuentas MT5 demo en el mismo broker/VPS, mismo setup, sin activar eval aún.

**Setup:**
| Cuenta | Rol |
|--------|-----|
| A (Santiago) | EA natural: long en cruce alcista, short en bajista |
| B (hermana) | Copiador **inverso** o EA espejo |

**Checklist diario (5 min):**
- [ ] ¿Entran trades solo 8:00–10:00?
- [ ] ¿Máx 2 trades/día por cuenta?
- [ ] ¿A y B van en direcciones opuestas?
- [ ] ¿Una equity sube y la otra baja?
- [ ] ¿SL en < 2 min?

**Criterio para pasar a “eval en serio” (semana 2):**
- Una cuenta **≥ +5%** (~$250) y la otra **≤ -3%** → el par funciona; seguir
- Ambas cerca de 0 después de 10 días → revisar copiador/offset
- Una tocó **-8%** y la otra no llega a +5% → parar y debug

---

## Fase 3 — Eval WS (live demo prop firm)

**Pregunta:** ¿Pasamos fase 1 (+8% = $400)?

- Activar guardián: **parar ambos robots al +8%** en la ganadora
- Mínimo **4 días** con trades (regla WS)
- Cuando una pasa → apagar todo; la otra probablemente en breach

**Objetivo:** 1 cuenta a fase 2, no 2.

---

## Resumen para tu hermana

| Fase | Dónde | Tiempo | Qué validamos |
|------|-------|--------|---------------|
| 1 Lab | Ordenador | Horas | ¿Históricamente el par gana en semanas? |
| 2 Demo | VPS + MT5 | 1–2 sem | ¿Ahora funciona el espejo? |
| 3 Eval | WS regaladas | 3–14 días | ¿Una pasa +8%? |

**No saltéis la fase 2.** Las evals regaladas pueden ser vuestra fase 2 si observáis 3–5 días antes de confiar en el robot.

---

## Comando rápido (terminal)

```bash
cd /Users/santiago/Documents/Personal/trading
python scripts/hedge_validate.py
```

Imprime pass rate 7/14/30d con defaults del curso.
