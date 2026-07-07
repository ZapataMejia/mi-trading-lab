# Cómo crear una nueva estrategia

## 1. Estrategia Polymarket (lo más común)

Copia `template_polymarket.py` a `strategies/polymarket/mi_estrategia.py`.

Edita los atributos de clase:

| Atributo | Tipo | Ejemplo |
|---|---|---|
| `name` | str | `"Mi estrategia"` |
| `description` | str | breve descripción |
| `threshold` | float | `0.15` = 15 pp mínimo de edge |
| `asset_filter` | tuple | `("sol", "btc")` o `()` para todos |
| `skip_hours_utc` | tuple | `(21, 23)` |
| `skip_weekdays` | tuple | `("Saturday",)` |
| `only_weekdays` | tuple | `("Monday", "Tuesday")` |
| `min_volume_usd` | float | `5000.0` |
| `max_seconds_to_resolution` | int | `300` = últimos 5 min, `0` = sin límite |
| `dataset` | str | `"hourly_full"` o `"v4_real"` |

Agrega el import en `strategies/polymarket/__init__.py`:

```python
from strategies.polymarket import mi_estrategia
```

Y listo. Aparece en la web app al refrescar.

## 2. Estrategia Crypto (en desarrollo)

Coming soon — adapter para Binance/Bybit perpetuos.

## 3. Hablar con Claude

Lo más rápido es decirme en Cursor:

> "Hagamos una estrategia que opere solo SOL los viernes con edge >25pp"

Y yo te creo el archivo.
