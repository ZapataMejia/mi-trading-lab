import sys
import pandas as pd

path = sys.argv[1] if len(sys.argv) > 1 else "data/agotamiento/trades_faithful_NQDK_both_tp5.0_sr0.csv"
tr = pd.read_csv(path)
tr["entry_time"] = pd.to_datetime(tr["entry_time"], utc=True)
tr["exit_time"] = pd.to_datetime(tr["exit_time"], utc=True)
tr["mins"] = (tr["exit_time"] - tr["entry_time"]).dt.total_seconds() / 60
tr["risk_pts"] = (tr["entry"] - tr["sl"]).abs()
tr["risk_pct"] = tr["risk_pts"] / tr["entry"] * 100

print(f"Archivo: {path}")
print(f"Total trades: {len(tr)}")
print()
print("--- DURACION de los trades (minutos) ---")
print(f"  mediana: {tr['mins'].median():.1f} min   media: {tr['mins'].mean():.1f} min")
print(f"  <= 1 min:  {(tr['mins'] <= 1).mean() * 100:.0f}%")
print(f"  <= 5 min:  {(tr['mins'] <= 5).mean() * 100:.0f}%")
print(f"  <= 15 min: {(tr['mins'] <= 15).mean() * 100:.0f}%")
print()
print("--- TAMANO DEL STOP (riesgo entrada->SL) ---")
print(f"  mediana riesgo: {tr['risk_pts'].median():.2f} pts  =  {tr['risk_pct'].median():.3f}% del precio")
print(f"  riesgo < 0.05% del precio: {(tr['risk_pct'] < 0.05).mean() * 100:.0f}% de los trades")
print()
print("--- COMO MUEREN ---")
print(tr["reason"].value_counts().to_string())
print()
los = tr[tr["reason"] == "SL"]
if len(los):
    print(f"De los SL: duracion mediana = {los['mins'].median():.1f} min")
    print(f"  % de SL que mueren en <= 1 min: {(los['mins'] <= 1).mean() * 100:.0f}%")
    print(f"  % de SL que mueren en <= 2 min: {(los['mins'] <= 2).mean() * 100:.0f}%")
