"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Line, LineChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";
import { Loader2, Play, X, Plus } from "lucide-react";
import { api, formatCurrency } from "@/lib/api";
import { PeriodSelector, type PeriodRange } from "@/components/PeriodSelector";
import { useToast } from "@/components/Toast";
import { fetchErrorMessage } from "@/lib/fetch-error";
import type { BacktestResult, Strategy } from "@/lib/types";
import { useCapabilities } from "@/components/CapabilitiesProvider";
import { marketBacktestAvailable } from "@/lib/capabilities";

const COLORS = ["#2563eb", "#16a34a", "#dc2626", "#d97706", "#7c3aed", "#0891b2"];

const MARKET_GROUPS: { key: string; label: string; hint?: string }[] = [
  { key: "crypto_perp", label: "Crypto", hint: "Breakout, mean reversion, trend…" },
  { key: "polymarket", label: "Polymarket", hint: "Bots V1 · V2B · V4…" },
];

function groupStrategies(strategies: Strategy[]) {
  const groups: Record<string, Strategy[]> = {};
  for (const s of strategies) {
    (groups[s.market_type] ||= []).push(s);
  }
  return groups;
}

function StrategyPickButton({
  s,
  selectedCount,
  onToggle,
  disabled,
}: {
  s: Strategy;
  selectedCount: number;
  onToggle: (id: string) => void;
  disabled?: boolean;
}) {
  const blocked = disabled || selectedCount >= 6;
  return (
    <button
      key={s.id}
      onClick={() => !disabled && onToggle(s.id)}
      disabled={blocked}
      className="text-xs px-2.5 py-1 rounded-md inline-flex items-center gap-1.5"
      style={{
        background: "var(--bg-hover)",
        color: "var(--text-muted)",
        border: "1px solid var(--border)",
        cursor: blocked ? "not-allowed" : "pointer",
        opacity: blocked ? 0.4 : 1,
      }}
      title={disabled ? "No disponible en este servidor" : undefined}
    >
      <Plus size={11} /> {s.name}
    </button>
  );
}

function ComparePageInner() {
  const params = useSearchParams();
  const initialIds = params.get("ids")?.split(",").filter(Boolean) || [];

  const [allStrategies, setAllStrategies] = useState<Strategy[]>([]);
  const [selected, setSelected] = useState<string[]>(initialIds);
  const [results, setResults] = useState<Record<string, BacktestResult>>({});
  const [period, setPeriod] = useState<PeriodRange>({ preset: "1y" });
  const [running, setRunning] = useState(false);
  const toast = useToast();
  const caps = useCapabilities();

  function marketEnabled(key: string): boolean {
    if (key === "polymarket") return caps.polymarket;
    if (key === "crypto_perp") return caps.crypto;
    return marketBacktestAvailable(caps, key);
  }

  useEffect(() => {
    api.listStrategies()
      .then((r) => setAllStrategies(r.strategies))
      .catch((e) => toast.push(fetchErrorMessage(e) || "No se pudo cargar estrategias", "error"));
  }, [toast]);

  function toggle(id: string) {
    setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id].slice(0, 6)));
  }

  async function runAll() {
    if (selected.length === 0) {
      toast.push("Selecciona al menos una estrategia", "info");
      return;
    }
    const blocked = selected.filter((id) => {
      const s = allStrategies.find((x) => x.id === id);
      return s && !marketBacktestAvailable(caps, s.market_type);
    });
    if (blocked.length > 0) {
      toast.push("Algunas estrategias seleccionadas no están disponibles en este servidor", "error");
      return;
    }
    setRunning(true);
    setResults({});
    try {
      const promises = selected.map((id) =>
        api.runBacktest({
          strategy_id: id,
          period_start: period.start,
          period_end: period.end,
          trades_limit: 0,
          equity_points: 250,
        }),
      );
      const settled = await Promise.allSettled(promises);
      const out: Record<string, BacktestResult> = {};
      settled.forEach((s, i) => {
        if (s.status === "fulfilled") out[selected[i]] = s.value;
        else toast.push(`Error: ${fetchErrorMessage(s.reason)}`, "error");
      });
      setResults(out);
      toast.push(`${Object.keys(out).length} backtests completados`, "success");
    } finally {
      setRunning(false);
    }
  }

  // Merge equity curves para chart conjunto
  const chartData = (() => {
    if (Object.keys(results).length === 0) return [];
    const allTs = new Set<number>();
    Object.values(results).forEach((r) =>
      r.equity_curve.forEach((p) => allTs.add(new Date(p.timestamp).getTime())),
    );
    const sorted = Array.from(allTs).sort((a, b) => a - b);
    return sorted.map((ts) => {
      const row: Record<string, number> = { ts };
      Object.entries(results).forEach(([id, r]) => {
        // tomar el último equity point con ts <= current
        let last: number | undefined;
        for (const p of r.equity_curve) {
          if (new Date(p.timestamp).getTime() <= ts) last = p.bankroll;
          else break;
        }
        if (last !== undefined) row[id] = last;
      });
      return row;
    });
  })();

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight" style={{ color: "var(--text)" }}>
          Comparar estrategias
        </h1>
        <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
          Hasta 6 a la vez · compara bots de Polymarket o estrategias crypto (no forex)
        </p>
      </header>

      {/* Selector */}
      <div className="card p-4 mb-4">
        <div className="flex items-center gap-2 flex-wrap mb-3">
          <span className="text-xs uppercase tracking-wider mr-2" style={{ color: "var(--text-muted)" }}>
            Seleccionadas ({selected.length}/6):
          </span>
          {selected.length === 0 && (
            <span className="text-sm" style={{ color: "var(--text-faint)" }}>
              Click en las estrategias abajo para agregar
            </span>
          )}
          {selected.map((id, i) => {
            const s = allStrategies.find((x) => x.id === id);
            return (
              <span
                key={id}
                className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-md"
                style={{ background: COLORS[i % COLORS.length] + "22", color: COLORS[i % COLORS.length] }}
              >
                <span style={{ width: 8, height: 8, borderRadius: 999, background: COLORS[i % COLORS.length] }} />
                {s?.name || id.split(".").pop()}
                <button onClick={() => toggle(id)} className="ml-1 opacity-60 hover:opacity-100">
                  <X size={11} />
                </button>
              </span>
            );
          })}
        </div>
        <div className="space-y-3 pt-3 border-t" style={{ borderColor: "var(--border)" }}>
          {(() => {
            const available = allStrategies.filter((s) => !selected.includes(s.id));
            const grouped = groupStrategies(available);
            const ordered = MARKET_GROUPS.filter((g) => (grouped[g.key]?.length ?? 0) > 0);
            const otherKeys = Object.keys(grouped).filter((k) => !MARKET_GROUPS.some((g) => g.key === k));

            if (available.length === 0) {
              return (
                <p className="text-sm" style={{ color: "var(--text-faint)" }}>
                  Ya seleccionaste todas las disponibles (máx. 6).
                </p>
              );
            }

            return (
              <>
                {ordered.map(({ key, label, hint }) => (
                  <div key={key}>
                    <div className="text-[10px] uppercase tracking-wider mb-2" style={{ color: "var(--text-faint)" }}>
                      {label}
                      {hint && (
                        <span className="normal-case tracking-normal font-normal ml-1" style={{ color: "var(--text-muted)" }}>
                          · {hint}
                        </span>
                      )}
                      {!marketEnabled(key) && (
                        <span className="normal-case tracking-normal font-normal ml-2" style={{ color: "var(--red)" }}>
                          · no disponible en línea
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      {grouped[key]!.map((s) => (
                        <StrategyPickButton
                          key={s.id}
                          s={s}
                          selectedCount={selected.length}
                          onToggle={toggle}
                          disabled={!marketEnabled(key)}
                        />
                      ))}
                    </div>
                  </div>
                ))}
                {otherKeys.map((key) => (
                  <div key={key}>
                    <div className="text-[10px] uppercase tracking-wider mb-2" style={{ color: "var(--text-faint)" }}>
                      {key}
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      {grouped[key]!.map((s) => (
                        <StrategyPickButton key={s.id} s={s} selectedCount={selected.length} onToggle={toggle} />
                      ))}
                    </div>
                  </div>
                ))}
              </>
            );
          })()}
        </div>
      </div>

      <div className="card p-3 mb-4 flex items-center justify-between gap-4 flex-wrap">
        <PeriodSelector value={period} onChange={setPeriod} />
        <button onClick={runAll} disabled={running || selected.length === 0} className="btn-primary inline-flex items-center gap-2">
          {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
          {running ? "Corriendo backtests..." : `Comparar ${selected.length || ""}`}
        </button>
      </div>

      {/* Equity chart */}
      {chartData.length > 0 && (
        <section className="card p-5 mb-4">
          <h3 className="text-sm font-semibold mb-4" style={{ color: "var(--text)" }}>
            Equity curves superpuestas
          </h3>
          <ResponsiveContainer width="100%" height={360}>
            <LineChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="ts"
                type="number"
                scale="time"
                domain={["dataMin", "dataMax"]}
                tickFormatter={(t) => new Date(t).toLocaleDateString("es-CO", { month: "short", day: "numeric" })}
                stroke="var(--text-faint)"
                fontSize={11}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                stroke="var(--text-faint)"
                fontSize={11}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `$${v.toLocaleString()}`}
                width={75}
              />
              <Tooltip
                contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                labelFormatter={(t) => new Date(t).toLocaleString("es-CO")}
                formatter={(value, name) => {
                  const num = typeof value === "number" ? value : Number(value ?? 0);
                  const id = String(name ?? "");
                  const s = allStrategies.find((x) => x.id === id);
                  return [formatCurrency(num), s?.name || id];
                }}
              />
              <Legend
                content={({ payload }) => (
                  <div className="flex flex-wrap gap-3 text-xs mt-2 justify-center">
                    {payload?.map((p) => {
                      const s = allStrategies.find((x) => x.id === p.dataKey);
                      return (
                        <span key={p.dataKey as string} className="inline-flex items-center gap-1.5" style={{ color: "var(--text-muted)" }}>
                          <span style={{ width: 10, height: 2, background: p.color }} />
                          {s?.name || (p.dataKey as string)}
                        </span>
                      );
                    })}
                  </div>
                )}
              />
              {selected.map((id, i) => (
                <Line
                  key={id}
                  type="monotone"
                  dataKey={id}
                  stroke={COLORS[i % COLORS.length]}
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </section>
      )}

      {/* Tabla comparativa */}
      {Object.keys(results).length > 0 && (
        <section className="card p-5">
          <h3 className="text-sm font-semibold mb-4" style={{ color: "var(--text)" }}>
            Métricas lado a lado
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ color: "var(--text-faint)" }}>
                  <th className="text-left font-medium pb-2.5 pr-4 text-xs uppercase tracking-wider">Estrategia</th>
                  <th className="text-right font-medium pb-2.5 pr-4 text-xs uppercase tracking-wider">Trades</th>
                  <th className="text-right font-medium pb-2.5 pr-4 text-xs uppercase tracking-wider">WR</th>
                  <th className="text-right font-medium pb-2.5 pr-4 text-xs uppercase tracking-wider">Bankroll final</th>
                  <th className="text-right font-medium pb-2.5 pr-4 text-xs uppercase tracking-wider">Profit</th>
                  <th className="text-right font-medium pb-2.5 pr-4 text-xs uppercase tracking-wider">Sharpe</th>
                  <th className="text-right font-medium pb-2.5 pr-4 text-xs uppercase tracking-wider">Max DD</th>
                  <th className="text-right font-medium pb-2.5 text-xs uppercase tracking-wider">Profit factor</th>
                </tr>
              </thead>
              <tbody>
                {selected.map((id, i) => {
                  const r = results[id];
                  if (!r) return null;
                  const positive = r.total_pnl >= 0;
                  return (
                    <tr key={id} className="border-t hover:bg-zinc-50/50" style={{ borderColor: "var(--border)" }}>
                      <td className="py-2.5 pr-4 inline-flex items-center gap-2">
                        <span style={{ width: 8, height: 8, borderRadius: 999, background: COLORS[i % COLORS.length] }} />
                        <span style={{ color: "var(--text)" }}>{r.strategy_name}</span>
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums" style={{ color: "var(--text-muted)" }}>
                        {r.metrics.n_trades.toLocaleString()}
                      </td>
                      <td
                        className="py-2.5 pr-4 text-right tabular-nums font-medium"
                        style={{ color: r.metrics.win_rate_pct >= 55 ? "var(--green)" : "var(--text)" }}
                      >
                        {r.metrics.win_rate_pct.toFixed(1)}%
                      </td>
                      <td
                        className="py-2.5 pr-4 text-right tabular-nums font-semibold"
                        style={{ color: positive ? "var(--green)" : "var(--red)" }}
                      >
                        {formatCurrency(r.final_bankroll)}
                      </td>
                      <td
                        className="py-2.5 pr-4 text-right tabular-nums"
                        style={{ color: positive ? "var(--green)" : "var(--red)" }}
                      >
                        {r.total_pnl >= 0 ? "+" : ""}
                        {formatCurrency(r.total_pnl)}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums" style={{ color: "var(--text-muted)" }}>
                        {r.metrics.sharpe.toFixed(2)}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums" style={{ color: "var(--red)" }}>
                        {r.metrics.max_drawdown_pct.toFixed(1)}%
                      </td>
                      <td className="py-2.5 text-right tabular-nums" style={{ color: "var(--text-muted)" }}>
                        {r.metrics.profit_factor !== null ? r.metrics.profit_factor.toFixed(2) : "∞"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<div className="p-8" style={{ color: "var(--text-muted)" }}>Cargando...</div>}>
      <ComparePageInner />
    </Suspense>
  );
}
