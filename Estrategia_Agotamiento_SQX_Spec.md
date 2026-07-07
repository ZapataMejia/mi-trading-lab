# Agotamiento → StrategyQuant X (AlgoWizard) — Spec de implementación

> Mapa exacto del pseudocódigo (`Estrategia_Agotamiento_Cristian.md`) a bloques de
> **AlgoWizard / StrategyQuant X v142**. Marca qué es **nativo** y qué requiere un
> **Custom Block / Custom Indicator** (snippet). Pensado para construir en el VPS sin perderse.
>
> Nota de honestidad: la estrategia es **discrecional** (lectura visual de S/R, estructura
> y manipulación). Aquí se automatiza su **núcleo mecánico**. El backtest validará ese
> núcleo, NO el "ojo" del trader. Ver §8 (qué NO captura el backtest).

---

## 0. Enfoque general

- **Timeframe primario = 1m** (ejecución / línea de agotamiento).
- **Estructura 5m** y **S/R 15m/30m/60m** se referencian como **timeframes superiores (MTF)**.
- Construimos una **versión sistematizada fiel**: fijamos los puntos "a ojo" (§9 del pseudocódigo)
  con reglas concretas para que el motor pueda ejecutarlas.
- Donde AlgoWizard no llega con bloques estándar → **Custom Indicator** (editor de SQX, snippet
  tipo Java). Cada uno está especificado en §3 con su lógica.

| Componente | ¿Cómo en SQX? |
|---|---|
| Módulo de arranque (lowest low desde apertura) | **Custom Indicator** |
| Retroceso de N velas + línea de agotamiento | **Custom Indicator** |
| Trigger de entrada (ruptura de la línea) | Bloque nativo (Cross) sobre el indicador custom |
| Estructura 5m alcista/bajista | Custom Indicator MTF (o bloques HH/HL en 5m) |
| Filtro S/R alta temporalidad | Custom Indicator (aprox.) — opcional en v1 |
| SL en último swing / TP por ratio | Money Management nativo (SL/TP "by signal") |
| Breakeven a 1:1 / 2:1 | MM nativo (Move SL to BE / a 0.5R) |
| Máx 3 trades/día, parar tras 1er SL | Filtros de sesión nativos + Custom (contador) |
| Ventanas horarias, cierre 13:00 | Time filter nativo + "Close at time" |

---

## 1. Datos requeridos (resolver ANTES de construir)

> **DECISIÓN FIJADA:** cuenta objetivo = **WS Funded** (CFD/MT5). Por tanto:
> instrumento **US100 (NAS100, Nasdaq index CFD)**, y el robot se exporta a **MetaTrader 5**.
> (No futuros/NinjaTrader; ese es el ecosistema de Cris pero no el de WS Funded.)
> WS Funded **permite EAs solo en planes de evaluación** (RAPID/CLASSIC/ULTRA), NO en "Instant".

- **Instrumento:** **US100 / NAS100** (CFD de Nasdaq) tal como lo nombre el broker de WS Funded.
  Para datos/backtest sirve también un proxy de índice Nasdaq si el feed de SQX no trae US100.
- **Timeframes a importar:** **1m** (primario) + **5m** (estructura). 15/30/60m opcionales
  para S/R (se pueden derivar del 5m con MTF).
- **Profundidad realista:** el "20 años" en **1m** casi nunca está disponible/limpio.
  - MNQ existe desde **2019**. NQ (full) desde 1999 pero 1-min de 20 años es difícil.
  - **Propuesta realista:** **5–8 años de 1m** (cubre regímenes alcistas, 2022 bajista, rangos).
    Si se quiere "20 años", hacerlo en **5m/15m** y aceptar menor fidelidad de la entrada de 1m.
- **Zona horaria / sesión:** configurar el instrumento a **ET** (o MT) y definir ventanas (§2).
  Confirmar el offset que usa el data feed (muchos vienen en UTC o broker-time).

> **Tarea siguiente:** abrir **Data manager** en SQX (VPS) y anotar: instrumentos disponibles,
> TFs, fecha inicio/fin del histórico, y zona horaria del feed.

---

## 2. Parámetros sistematizados (fijamos lo "a ojo")

| Parámetro | Valor v1 (fiel) | Nota |
|---|---|---|
| `SWING_N` (pivote) | **2** velas a cada lado | swing que "ve el ojo" |
| `RETRO_MIN_VELAS` | **3** velas continuas | dojis cuentan a favor |
| `LINEA_CON_MECHA` | **sí** | usa High/Low, no Close |
| `BUFFER_SL_TICKS` | **0** (swing exacto) | o 1–2 ticks si hace falta |
| `TP_RATIO` | **1.0** base; barrer **2.0 / 3.0** | v2 busca 3:1 |
| `BREAKEVEN` | a **1:1** mover SL a **0.5R**; a **2:1** mover a **BE** | §F del plan |
| `MAX_TRADES_DIA` | **3** | regla de disciplina |
| `STOP_TRAS_1ER_SL` | **sí** | si 1ª del día = SL → fuera |
| `VENTANA_ENTRADAS` | **09:30–11:30** (def. zona) | "no entrar tras 11:30 MT" |
| `CIERRE_FORZADO` | **13:00** (def. zona) | cerrar todo |
| `SESION` | Londres + NY | módulo de arranque |

> Estos valores ya están parametrizados en el backtester Python (`scripts/agotamiento_backtest.py`),
> así podremos **comparar** SQX vs Python para validar (§8).

---

## 3. Custom Indicators / Blocks necesarios (con lógica)

> En SQX: *Snippets → New → Indicator/Block*. Lógica en pseudocódigo (adaptar a la sintaxis del editor).

### 3.1. `ModuloArranque` (por barra, en 5m)
```
entrada: serie 5m, hora_apertura_sesion
estado: desde la apertura de sesión del día, trackear:
  moduloAlcista = LowestLow(desde apertura hasta barra actual)
  moduloBajista = HighestHigh(desde apertura hasta barra actual)
salida: moduloAlcista, moduloBajista  (se resetea cada día en la apertura)
```
Nativo posible: `Lowest(Low, barsSinceSessionStart)` si SQX expone "bars since session start";
si no, contador custom que resetea al cambiar de día/sesión.

### 3.2. `Retroceso + LineaAgotamiento` (en 1m)
```
contar velas bajistas consecutivas (Close<Open; doji cuenta como continua):
  n = nº de velas rojas seguidas hasta la barra previa
si n >= RETRO_MIN_VELAS:
  LineaAgotamientoAlcista = HighestHigh(de esas n velas)   # mecha incluida
  retrocesoValido = (LowestLow(de esas n velas) > moduloAlcista5m)  # respeta estructura
si no: LineaAgotamientoAlcista = NaN
(espejo para el caso bajista con velas verdes y LowestLow)
```

### 3.3. `Estructura5m` (MTF)
```
alcista = (último SwingHigh5m > SwingHigh5m previo) Y (último SwingLow5m > SwingLow5m previo)
bajista = espejo
SwingHigh/Low con SWING_N=2
```
Aprox. nativa: comparar `Highest(High,k)` y patrón HH/HL con bloques estándar.

### 3.4. `FiltroSR` (opcional v1, recomendado v2)
```
niveles = S/R de 60/30/15m (pivotes con >=3 toques)
cerca = |precio_entrada - nivel| <= MARGEN (p.ej. 0.15*ATR o X ticks)
compra_ok = NO (hay resistencia cerca por encima)
venta_ok  = NO (hay soporte cerca por debajo)
```
> v1: arrancar **sin** este filtro (más trades, baseline). v2: añadirlo y comparar.

---

## 4. Reglas de ENTRADA (AlgoWizard)

### Long (caso del video)
```
AND:
  1) Estructura5m == alcista
  2) Retroceso válido (3.2 retrocesoValido == true)
  3) Cross: High(1m) CRUZA POR ENCIMA de LineaAgotamientoAlcista   # ruptura
  4) Time filter: dentro de VENTANA_ENTRADAS
  5) (v2) FiltroSR.compra_ok == true
  6) Límites de sesión OK (§6): trades_hoy < 3 y no bloqueado por SL
→ BUY (a mercado, al cierre de la vela que rompe)
```

### Short (espejo)
```
AND:
  1) Estructura5m == bajista
  2) Retroceso válido (velas verdes, respeta moduloBajista)
  3) Cross: Low(1m) CRUZA POR DEBAJO de LineaAgotamientoBajista
  4) Time filter dentro de ventana
  5) (v2) FiltroSR.venta_ok == true
  6) Límites de sesión OK
→ SELL
```

> "Entrar en los últimos ~10s de la vela con cuerpo del lado correcto" (§C-9 v2) → en backtest
> se aproxima con **entrada al cierre de la barra 1m que rompe**. Es la traducción fiel posible.

---

## 5. SALIDAS (Money Management nativo)

- **Stop Loss:** en el **último swing** antes de la entrada (zona de riesgo en 1m).
  - Long: `SL = LowestLow(últimas K velas hasta el swing) - BUFFER`
  - SQX: SL "by signal" / precio custom (pasar el nivel del swing como precio de SL).
- **Take Profit:** `TP = entrada ± TP_RATIO * (|entrada - SL|)`.
  - SQX: TP "Risk:Reward" o precio custom. Barrer **1.0 / 2.0 / 3.0**.
- **Breakeven escalonado** (MM nativo "Move SL"):
  - a **+1R** → mover SL a **+0.5R**.
  - a **+2R** → mover SL a **BE** (0R).
- **Regla de oro:** sin cierre manual (el motor no lo hace; OK).

---

## 6. Límites de sesión y disciplina

- **Time filter** nativo: permitir entradas solo **09:30–11:30** (zona def.).
- **Cierre forzado** a **13:00**: "Close all at time" / exit por hora.
- **Máx 3 trades/día:** ajuste "max trades per day" si existe; si no, **Custom counter**
  que bloquea nuevas entradas al llegar a 3.
- **Parar tras 1er SL del día:** **Custom flag** — si el 1er trade del día cerró en SL,
  bloquear entradas el resto del día.
- (Opcional) no abrir alrededor de noticias de tasas → no automatizable sin feed de noticias;
  se omite en backtest y se anota como diferencia con el real.

---

## 7. Orden de construcción en el VPS (cuando toque)

1. **Data manager:** importar/confirmar Nasdaq 1m (+5m). Anotar rango y TZ.
2. Crear los **Custom Indicators** (§3) y compilarlos.
3. En **AlgoWizard**: armar entradas Long/Short (§4) usando esos indicadores.
4. Configurar **MM** (§5) y **time filters** (§6).
5. Backtest base (Long+Short, TP 1.0, sin FiltroSR) en el rango disponible.
6. Iterar: TP 2.0/3.0, con/sin FiltroSR, swing 2 vs 3, ventanas horarias.
7. Comparar contra el backtest Python (§8).
8. Evaluar contra **WS Funded** (siguiente entregable).

---

## 8. Qué NO captura el backtest (ser honestos)

- La **lectura discrecional** de S/R, manipulación de Londres/Asia y "contexto".
- "Entrar en los últimos 10s con cuerpo del lado correcto" → se aproxima con cierre de barra.
- Escalado discrecional con **ATM Soul** y cierres manuales por criterio (§G del plan).
- Noticias (tasas) → no hay filtro de noticias en el backtest.
- Slippage/comisiones reales de futuros (configurar costos realistas en SQX).

→ El backtest mide si el **núcleo mecánico** (impulso → retroceso 3 velas → ruptura de
línea con estructura a favor, SL al swing, TP por ratio) **tiene edge por sí solo**.
Si lo tiene, es base sólida; el "ojo" del trader sería un extra encima.

---

## 9. Validación cruzada (SQX ↔ Python)

- Correr en SQX el **mismo rango** y parámetros que ya probamos en Python (`data/agotamiento/`).
- Comparar: nº de trades, win rate, profit factor, max drawdown, curva de equity.
- Si difieren mucho → revisar definición de swing/retroceso/línea (lo más probable de divergir).

---

## 10. Criterios WS Funded (para la evaluación final)

> WS Funded = simulado, CFD/MT5. **EAs permitidos en planes de evaluación** (no en "Instant").
> **SL obligatorio dentro de 2 min** de abrir → nuestra estrategia pone SL en la entrada, cumple.
> Riesgo máx por "trading idea": **50% del DD diario** (evaluación).

Planes de evaluación (donde corre el EA):

| Plan | Fases | Target | DD diario | DD máx (estático) | 1er payout |
|---|---|---|---|---|---|
| **RAPID** | 1 | 10% | 4% | 6% | 30 días |
| **CLASSIC** | 2 | 8% → 5% | 5% | 8% | 15 días |
| **ULTRA** | 2 | 10% → 5% | 5% | 10% | 15 días |

- Tamaños: **$5k / $10k / $25k / $50k / $100k** (combinables hasta $400k).
- Máx lotes índices (ej.): $100k → 70 lots; $50k → 40; $25k → 20; $10k → 10; $5k → 5.
- Inactividad: breach a los 30 días sin operar.

**Pendiente de Juli (define el pass/fail del backtest):**
1. ¿Qué **plan**? (RAPID 1-fase vs CLASSIC vs ULTRA 2-fases).
2. ¿Qué **tamaño** de cuenta? ($5k–$100k).
3. Confirmar que es **evaluación** (no "Instant"), para que el EA esté permitido.

**Cómo lo mediremos en SQX (una vez elegido el plan):**
- Convertir los % a $ según el tamaño → fijar target, DD diario y DD máx.
- En el backtest, marcar si la curva habría **superado el target** sin violar
  el **DD diario** ni el **DD máx estático**, dentro de las reglas de sesión.
- Verificar que cada trade lleva **SL** (regla de los 2 min) y respeta el **riesgo por idea**.
```
