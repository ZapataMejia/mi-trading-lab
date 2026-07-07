# Exportar EURUSD M5 (Dukascopy) desde SQX en el VPS

Mismo rango que el backtest: **2017.01.03 – 2022.03.31**, timeframe **M5**.

---

## Opción A — Export desde Data Manager (recomendada)

1. **RDP** al VPS → abrir **StrategyQuant X** (`C:\SQX_143`).

2. Menú superior: **Data** → **Data Manager** (o icono de base de datos).

3. En la lista de datos, busca:
   - **EURUSD**
   - Timeframe: **M5**
   - Fuente: **Dukascopy** (o el nombre que usaste en el backtest, ej. `EURUSD_M1_dukas` resampleado — usa **el mismo** que en AlgoWizard).

4. Clic derecho sobre ese dataset → **Export** / **Export to CSV** / **Save as CSV**.
   - Si pide rango: **2017-01-03** hasta **2022-03-31**.

5. Guarda en una carpeta fácil, por ejemplo:
   ```
   C:\Users\Public\Downloads\EURUSD_M5.csv
   ```

6. **Copia el archivo a tu Mac** (arrastrar por RDP, Google Drive, o zip + descarga).

7. En el Mac: abre **http://localhost:3000/fondeo** → **Subir CSV M5** → selecciona el archivo.

### Formato esperado del CSV

Columnas (cabecera):
```
timestamp, open, high, low, close
```
o `time` en lugar de `timestamp`. El lab normaliza solo.

---

## Opción B — Si no ves "Export" en Data Manager

1. **Data** → **Data Manager** → selecciona EURUSD M5.

2. Prueba: menú **File** → **Export data** / **Export bars**.

3. O en **AlgoWizard**, pestaña de datos del proyecto `FondeoEMA`:
   - Anota el nombre exacto del dataset (ej. `EURUSD_M1_dukas` M5).
   - Vuelve a Data Manager con ese nombre.

4. Si SQX no exporta: copia la carpeta de datos crudos (soporte HobbyCode / foro SQX).
   Ruta típica:
   ```
   C:\SQX_143\user\data\
   ```
   Busca subcarpetas con `EURUSD` o `dukascopy`.

---

## Opción C — Nosotros descargamos en el Mac (sin VPS)

Si el VPS es incómodo, en el Mac (con el lab abierto):

```bash
cd /Users/santiago/Documents/Personal/trading
source .venv/bin/activate
bash scripts/fetch_and_research.sh
```

Eso descarga Dukascopy mes a mes (~1–2 h) y corre el research al terminar.
Log: `data/forex_cache/_nohup.log`

---

## Verificar que el CSV es correcto

En terminal Mac:

```bash
head -3 data/forex_cache/EURUSD_M5.csv
wc -l data/forex_cache/EURUSD_M5.csv
```

Esperado: **~350.000–400.000** filas para 5 años M5 (orden de magnitud).
Rango fechas: 2017-01 → 2022-03.

---

## Después de subir

1. Refresca **http://localhost:3000/fondeo** — debería mostrar el rango completo.
2. Avisame y corremos grid + te paso params para validar en SQX.
