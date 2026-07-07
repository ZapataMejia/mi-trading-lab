# Validar Liquidity Sweep SAFE en AlgoWizard (SQX)

Config ganadora del lab — **mejor estrategia EURUSD M5 para eval WS CLASSIC $5k** (vs EMA, Judas, Silver Bullet, ORB, London, filtros ADX/ATR).

## Parámetros exactos (AlgoWizard)

| Parámetro | Valor |
|-----------|-------|
| Símbolo | EURUSD |
| Timeframe | M5 |
| Capital | 5000 |
| Lookback | **36** barras |
| SL buffer | **3** pips |
| Risk % (MM) | **1.5** |
| TP ratio | **1.5** (R) |
| Sesión inicio | **700** (07:00 broker) |
| Sesión fin | **1400** (14:00 broker) |
| Max trades/día | **1** |
| Long + Short | ambos |

### Timezone

Lab usa **offset broker UTC+7** (hora del gráfico SQX ≈ EST+07 o equivalente).

Sesión operativa: **07:00–14:00 hora broker**.

---

## Instalación snippet

1. Copiar `sqx/indicators/LiquiditySweep.java` → SQX Code Editor → New Snippet → Indicator → pegar → **Compile**.
2. Ver `sqx/bundle/LEEME.txt` si usas carpeta `user/extend`.

## AlgoWizard — 2 reglas

**Long entry**
- Condición: `LiquiditySweep → LongEntry` **> 0**
- Action: Enter at Market
- SL: `LiquiditySweep → LongStop`
- TP: `LiquiditySweep → LongTP`

**Short entry**
- Condición: `LiquiditySweep → ShortEntry` **> 0**
- Action: Enter at Market
- SL: `LiquiditySweep → ShortStop`
- TP: `LiquiditySweep → ShortTP`

**Money Management:** Risk fixed **1.5%** · Max **1** posición · Max **1** trade/día (doble filtro con indicador).

Parámetros del indicador en ambas reglas: **36 / 1.5 / 1.5 / 3 / 700 / 1400 / 1**.

---

## Datos backtest (comparar con lab)

- CSV: mismo `EURUSD_M5` Dukascopy que en Mac
- Rango validación: **2022-01-01 → 2024-10-30**

### Referencia lab (debe cuadrar ±10%)

| Métrica | Lab |
|---------|-----|
| Trades | ~734 |
| PnL | positivo (varía por dataset) |
| Pass ventanas 30d OOS | **~44%** (7/16) |
| DD diario máx (eval) | **~1.98%** |
| DD estático (eval) | **~-1.6%** |

### Rango 2026 (forward reciente)

| Mes | PnL lab | ¿Pasa eval? |
|-----|---------|:-----------:|
| Mar | +$408 | Sí |
| Abr | +$446 | Sí |
| Feb | -$376 | No |
| Jun | -$226 | No |
| Ene→jul | +$489 | Sí |

---

## Si SQX no cuadra

1. Verificar **timezone** del chart (sesión 700–1400 broker)
2. Mismo CSV / mismas fechas
3. MM **1.5%** (no 2.1%)
4. SL/TP desde outputs del indicador (no SL fijo %)

---

## ¿Es la mejor que tenemos?

**Sí, para EURUSD M5 + reglas WS $5k**, según todo el lab:

| Estrategia | Pass 30d OOS |
|------------|:------------:|
| **Liquidity Sweep SAFE** | **~44%** |
| Liq Sweep AGGR | ~44% (peor DD) |
| EMA cross | 0% |
| ICT Judas | 0% |
| Silver Bullet | 0% |
| ORB + ADX | 0% |
| + filtros ADX/ATR (192 combos) | peor que SAFE |

Plan: **validar en SQX → demo WS 2 sem → eval cuenta 1**.

Config JSON: `data/forex_cache/liq_sweep_safe_config.json`
