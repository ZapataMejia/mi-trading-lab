"""Minería de features: ¿qué contexto predice ganadores? Validación train/test."""
import sys
import numpy as np
import pandas as pd

path = sys.argv[1] if len(sys.argv) > 1 else "data/agotamiento/trades_faithful_NQDK_both_tp3.0_sr0.csv"
tr = pd.read_csv(path)
tr["entry_time"] = pd.to_datetime(tr["entry_time"], utc=True)
tr["year"] = tr["entry_time"].dt.year
tr["R"] = tr["r_mult"]  # +3 si TP, -1 si SL (neto de slippage)

split_year = 2020
train = tr[tr["year"] < split_year]
test = tr[tr["year"] >= split_year]

print(f"Total {len(tr)} trades | TRAIN(<{split_year}) {len(train)} | TEST(>= {split_year}) {len(test)}")
be = 0.0
print(f"Expectancy base (R/trade):  global {tr['R'].mean():.3f}   train {train['R'].mean():.3f}   test {test['R'].mean():.3f}")
print(f"Win rate base: global {(tr['R']>0).mean()*100:.1f}%   (break-even necesita ~25% con TP3)")
print("=" * 78)


def show_cat(name, col):
    print(f"\n### {name} (expectancy R y win% ; n)  — TRAIN | TEST")
    g_tr = train.groupby(col)["R"].agg(["mean", "count"])
    g_te = test.groupby(col)["R"].agg(["mean", "count"])
    wr_tr = train.groupby(col)["R"].apply(lambda s: (s > 0).mean() * 100)
    wr_te = test.groupby(col)["R"].apply(lambda s: (s > 0).mean() * 100)
    keys = sorted(set(g_tr.index) | set(g_te.index))
    for k in keys:
        mtr = g_tr["mean"].get(k, np.nan); ntr = int(g_tr["count"].get(k, 0))
        mte = g_te["mean"].get(k, np.nan); nte = int(g_te["count"].get(k, 0))
        wtr = wr_tr.get(k, np.nan); wte = wr_te.get(k, np.nan)
        robust = "  <== + en AMBOS" if (mtr > 0.05 and mte > 0.05 and ntr > 100 and nte > 50) else ""
        print(f"  {str(k):>6}:  R {mtr:+.3f}/{mte:+.3f}   win {wtr:4.1f}%/{wte:4.1f}%   "
              f"n {ntr:5d}/{nte:5d}{robust}")


def show_cont(name, col, q=5):
    print(f"\n### {name} (quintiles por TRAIN)  — TRAIN | TEST")
    s = train[col].dropna()
    if len(s) < 100:
        print("  (pocos datos)")
        return
    edges = np.unique(np.quantile(s, np.linspace(0, 1, q + 1)))
    lab = [f"{edges[j]:.3f}-{edges[j+1]:.3f}" for j in range(len(edges) - 1)]
    tr_b = pd.cut(train[col], edges, labels=lab, include_lowest=True)
    te_b = pd.cut(test[col], edges, labels=lab, include_lowest=True)
    for k in lab:
        a = train[tr_b == k]["R"]; b = test[te_b == k]["R"]
        if len(a) == 0:
            continue
        robust = "  <== + en AMBOS" if (a.mean() > 0.05 and len(b) and b.mean() > 0.05 and len(a) > 100 and len(b) > 50) else ""
        print(f"  {k:>16}:  R {a.mean():+.3f}/{(b.mean() if len(b) else float('nan')):+.3f}   "
              f"win {(a>0).mean()*100:4.1f}%/{((b>0).mean()*100) if len(b) else float('nan'):4.1f}%   "
              f"n {len(a):5d}/{len(b):5d}{robust}")


show_cat("DIRECCION", "dir")
show_cat("HORA (ET)", "hour")
show_cat("DIA SEMANA (0=lun)", "dow")
show_cat("A FAVOR DE TENDENCIA (above_ma)", "above_ma")
show_cat("VELAS DEL RETROCESO (run)", "run")
show_cont("RIESGO % del precio", "risk_pct")
show_cont("VOLATILIDAD % (ATR/precio)", "vol_pct")
show_cont("EXTENSION desde modulo %", "dist_module_pct")
show_cont("DISTANCIA a nivel dia previo %", "dist_level_pct")
print("\n" + "=" * 78)
print("Un edge REAL = bins con R positivo en TRAIN **y** TEST (marcados '<== + en AMBOS').")
