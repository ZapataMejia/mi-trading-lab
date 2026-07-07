"""Impacto de los límites de ejecución sobre los trades REALES del live.

El dataset histórico de 1 año solo tiene la PRIMERA señal de cada mercado
(minuto 1-4), nunca las de endgame, así que no sirve para backtestear la
estrategia endgame. La única data real de endgame son las operaciones que el
bot ya ejecutó en Polymarket.

Acá codifico esas operaciones (del historial de Polymarket) y simulo qué
hubiera pasado con los límites nuevos:
    max_fill_price = 0.70   (no perseguir favoritos caros)
    min_poly_price = 0.05   (no comprar longshots de 1¢)

Uso:
    python3 scripts/limits_on_live_trades.py
"""
from __future__ import annotations

from dataclasses import dataclass, field

MAX_FILL_PRICE = 0.70
MIN_POLY_PRICE = 0.05


@dataclass
class Trade:
    fecha: str
    mercado: str
    lado: str                       # "UP" / "DOWN"
    fills: list[tuple[float, float]]  # (precio, costo_usd)
    cobro: float                    # redención (0 si perdió)
    gano: bool

    @property
    def costo(self) -> float:
        return sum(c for _, c in self.fills)

    @property
    def avg_fill(self) -> float:
        # promedio ponderado por costo (proxy del precio pagado)
        tot = self.costo
        return sum(p * c for p, c in self.fills) / tot if tot else 0.0

    @property
    def neto(self) -> float:
        return self.cobro - self.costo

    def bloqueado(self) -> str | None:
        if self.avg_fill < MIN_POLY_PRICE:
            return f"longshot ({self.avg_fill*100:.1f}¢ < {MIN_POLY_PRICE*100:.0f}¢)"
        if self.avg_fill > MAX_FILL_PRICE:
            return f"caro ({self.avg_fill*100:.1f}¢ > {MAX_FILL_PRICE*100:.0f}¢)"
        return None


# Historial real de Polymarket (compras + redención/pérdida)
TRADES = [
    Trade("6/19", "ETH 8AM", "UP",   [(0.865, 50.50), (0.880, 19.89)], 80.94, True),
    Trade("6/19", "SOL 7AM", "DOWN", [(0.813, 45.33)],                  55.76, True),
    Trade("6/17", "SOL 9PM", "UP",   [(0.011, 53.47)],                   0.00, False),
    Trade("6/17", "XRP 2PM", "DOWN", [(0.782, 17.92), (0.782, 50.80)],  87.84, True),
    Trade("6/17", "SOL 10AM","UP",   [(0.810, 50.70)],                   0.00, False),
    Trade("6/16", "BTC 6PM", "UP",   [(0.487, 27.30)],                  56.01, True),
    Trade("6/16", "ETH 6PM", "UP",   [(0.243, 10.20), (0.331, 40.68)],   0.00, False),
    Trade("6/15", "BTC 8PM", "DOWN", [(0.932, 50.25), (0.656, 51.26)], 132.05, True),
]


def main() -> None:
    print("Impacto de límites sobre trades REALES del live (endgame)\n")
    print(f"  max_fill_price = {MAX_FILL_PRICE}   min_poly_price = {MIN_POLY_PRICE}\n")
    print(f"  {'Fecha':<5} {'Mercado':<9} {'Lado':<4} {'fill':>6} "
          f"{'neto':>9}  {'¿con límites?'}")
    print("  " + "-" * 64)

    base_total = 0.0
    lim_total = 0.0
    base_w = base_l = lim_w = lim_l = 0
    blocked_loss = blocked_win = 0
    saved = foregone = 0.0

    for t in TRADES:
        base_total += t.neto
        if t.gano:
            base_w += 1
        else:
            base_l += 1
        razon = t.bloqueado()
        if razon is None:
            lim_total += t.neto
            if t.gano:
                lim_w += 1
            else:
                lim_l += 1
            estado = "✓ se toma"
        else:
            estado = f"✗ bloqueado: {razon}"
            if t.neto < 0:
                blocked_loss += 1
                saved += -t.neto
            else:
                blocked_win += 1
                foregone += t.neto
        print(f"  {t.fecha:<5} {t.mercado:<9} {t.lado:<4} "
              f"{t.avg_fill*100:>5.1f}¢ {t.neto:>+9.2f}  {estado}")

    print("  " + "-" * 64)
    print(f"\n  BASELINE (todo):   {base_w}W/{base_l}L   PnL neto = ${base_total:+.2f}")
    print(f"  +LÍMITES (filtra): {lim_w}W/{lim_l}L   PnL neto = ${lim_total:+.2f}")
    print(f"\n  Pérdidas evitadas: {blocked_loss}  (${saved:+.2f} ahorrados)")
    print(f"  Ganancias cedidas: {blocked_win}  (${-foregone:+.2f} no ganados)")
    print(f"  Mejora neta:       ${lim_total - base_total:+.2f}  "
          f"({100*(lim_total-base_total)/abs(base_total):+.0f}% sobre el baseline)")
    print(f"\n  Trades ejecutados: {base_w+base_l} → {lim_w+lim_l} "
          f"({100*(lim_w+lim_l)/(base_w+base_l):.0f}% del volumen)")


if __name__ == "__main__":
    main()
