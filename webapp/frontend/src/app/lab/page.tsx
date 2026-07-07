"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Loader2, Play, FlaskConical, Grid3x3, Target, ArrowRight } from "lucide-react";
import { Line, LineChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Cell } from "recharts";
import { api, formatCurrency } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { fetchErrorMessage } from "@/lib/fetch-error";
import { PeriodSelector, type PeriodRange } from "@/components/PeriodSelector";
import { useCapabilities } from "@/components/CapabilitiesProvider";
import type { Strategy } from "@/lib/types";

interface WalkForwardWindow {
  index: number;
  period_start: string;
  period_end: string;
  n_trades: number;
  win_rate_pct: number;
  total_pnl: number;
  total_pnl_pct: number;
  sharpe: number;
  sortino: number;
  max_drawdown_pct: number;
  profit_factor: number | null;
}

interface GridResult {
  params: Record<string, number | string>;
  n_trades: number;
  win_rate_pct: number;
  total_pnl: number;
  total_pnl_pct: number;
  sharpe: number;
  max_drawdown_pct: number;
  profit_factor: number | null;
}

import { getApiBase } from "@/lib/api-base";

function LabPageInner() {
  const searchParams = useSearchParams();
  const initialMarket = searchParams.get("mercado") === "poly" ? "poly" : "forex";
  const [market, setMarket] = useState<"poly" | "forex">(initialMarket);
  const [mode, setMode] = useState<"wf" | "grid">("wf");
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [strategyId, setStrategyId] = useState<string>("");
  const [period, setPeriod] = useState<PeriodRange>({ preset: "1y" });
  const toast = useToast();
  const caps = useCapabilities();

  useEffect(() => {
    if (!caps.polymarket && market === "poly") setMarket("forex");
  }, [caps.polymarket, market]);

  useEffect(() => {
    api.listStrategies("polymarket")
      .then((r) => {
        setStrategies(r.strategies);
        if (r.strategies.length > 0) setStrategyId(r.strategies[0].id);
      })
      .catch((e) => toast.push(fetchErrorMessage(e) || "No se pudieron cargar estrategias", "error"));
  }, [toast]);

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight inline-flex items-center gap-2" style={{ color: "var(--text)" }}>
          <FlaskConical size={20} strokeWidth={1.75} />
          Lab · Laboratorio
        </h1>
        <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
          Herramientas avanzadas (walk-forward, grid search) para bots de Polymarket.
          Para forex WS usa el <Link href="/fondeo/liquidity-sweep" className="underline" style={{ color: "var(--accent)" }}>simulador</Link>.
        </p>
      </header>

      <div className="flex gap-2 mb-4">
        <button
          type="button"
          onClick={() => setMarket("forex")}
          className="px-4 py-2 rounded-lg text-sm border inline-flex items-center gap-2"
          style={{
            borderColor: market === "forex" ? "var(--accent)" : "var(--border)",
            background: market === "forex" ? "color-mix(in srgb, var(--accent) 10%, var(--bg-card))" : "var(--bg-hover)",
            color: market === "forex" ? "var(--accent)" : "var(--text-muted)",
            fontWeight: market === "forex" ? 600 : 400,
          }}
        >
          <Target size={16} />
          Forex · WS Funded
        </button>
        <button
          type="button"
          onClick={() => caps.polymarket && setMarket("poly")}
          disabled={!caps.polymarket}
          className="px-4 py-2 rounded-lg text-sm border inline-flex items-center gap-2"
          style={{
            borderColor: market === "poly" ? "var(--accent)" : "var(--border)",
            background: market === "poly" ? "color-mix(in srgb, var(--accent) 10%, var(--bg-card))" : "var(--bg-hover)",
            color: market === "poly" ? "var(--accent)" : "var(--text-muted)",
            fontWeight: market === "poly" ? 600 : 400,
            opacity: caps.polymarket ? 1 : 0.45,
            cursor: caps.polymarket ? "pointer" : "not-allowed",
          }}
          title={!caps.polymarket ? "Polymarket solo en versión local" : undefined}
        >
          <FlaskConical size={16} />
          Polymarket · Bots
        </button>
      </div>

      {market === "forex" ? (
        <div className="space-y-4">
          <div
            className="card p-6 border"
            style={{ borderColor: "var(--green)", background: "color-mix(in srgb, var(--green) 6%, var(--bg-card))" }}
          >
            <h2 className="text-lg font-semibold mb-2" style={{ color: "var(--text)" }}>
              Liquidity Sweep SAFE — EURUSD M5
            </h2>
            <p className="text-sm mb-4 max-w-2xl" style={{ color: "var(--text-muted)" }}>
              Simulador con reglas WS CLASSIC $5k: gráfico de compras/ventas, evaluación mes a mes (2026) y backtest histórico.
              Temporalidad recomendada: <strong>5 minutos</strong>.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link href="/fondeo/liquidity-sweep" className="btn-primary inline-flex items-center gap-2">
                Abrir simulador
                <ArrowRight size={16} />
              </Link>
              <Link href="/fondeo" className="btn-secondary inline-flex items-center gap-2">
                Curso EMA Cross
                <ArrowRight size={16} />
              </Link>
            </div>
          </div>
          <div className="card p-4 text-sm" style={{ color: "var(--text-muted)" }}>
            <strong style={{ color: "var(--text)" }}>Atajos para probar:</strong>
            <ul className="mt-2 space-y-1 list-disc pl-5">
              <li>Validación 2022–2024 → resumen anual (~735 trades)</li>
              <li>Simular un año → bloque “mes a mes” en el simulador WS</li>
              <li>Ene–Mar 2026 → gráfico con triángulos compra/venta</li>
            </ul>
          </div>
        </div>
      ) : (
        <>
        <div className="card p-4 mb-4">
        <div className="flex items-center gap-2 mb-4">
          <button
            onClick={() => setMode("wf")}
            className="px-3 py-1.5 rounded-md text-sm transition-colors inline-flex items-center gap-1.5"
            style={{
              background: mode === "wf" ? "var(--bg-active)" : "transparent",
              color: mode === "wf" ? "var(--text)" : "var(--text-muted)",
              fontWeight: mode === "wf" ? 500 : 400,
            }}
          >
            <FlaskConical size={14} /> Walk-forward
          </button>
          <button
            onClick={() => setMode("grid")}
            className="px-3 py-1.5 rounded-md text-sm transition-colors inline-flex items-center gap-1.5"
            style={{
              background: mode === "grid" ? "var(--bg-active)" : "transparent",
              color: mode === "grid" ? "var(--text)" : "var(--text-muted)",
              fontWeight: mode === "grid" ? 500 : 400,
            }}
          >
            <Grid3x3 size={14} /> Grid search
          </button>
        </div>

        <div className="grid md:grid-cols-2 gap-3">
          <div>
            <label className="text-xs uppercase tracking-wider block mb-1.5" style={{ color: "var(--text-muted)" }}>
              Estrategia
            </label>
            <select value={strategyId} onChange={(e) => setStrategyId(e.target.value)} className="w-full">
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs uppercase tracking-wider block mb-1.5" style={{ color: "var(--text-muted)" }}>
              Periodo
            </label>
            <PeriodSelector value={period} onChange={setPeriod} />
          </div>
        </div>
        </div>

      {mode === "wf" ? <WalkForwardPanel strategyId={strategyId} period={period} toast={toast} /> : <GridSearchPanel strategyId={strategyId} period={period} toast={toast} />}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
function WalkForwardPanel({ strategyId, period, toast }: { strategyId: string; period: PeriodRange; toast: ReturnType<typeof useToast> }) {
  const [nWindows, setNWindows] = useState(6);
  const [running, setRunning] = useState(false);
  const [data, setData] = useState<{ windows: WalkForwardWindow[]; summary: Record<string, number> } | null>(null);

  async function run() {
    if (!strategyId) return;
    setRunning(true);
    try {
      const res = await fetch(`${getApiBase()}/api/advanced/walk-forward`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy_id: strategyId, n_windows: nWindows, period_start: period.start, period_end: period.end }),
      });
      if (!res.ok) throw new Error(await res.text());
      const j = await res.json();
      setData(j);
      toast.push(`${nWindows} ventanas analizadas · ${j.summary.consistency_pct}% consistencia`, "success");
    } catch (e) {
      toast.push(`Error: ${String(e)}`, "error");
    } finally {
      setRunning(false);
    }
  }

  return (
    <>
      <div className="card p-4 mb-4 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 text-sm">
          <label style={{ color: "var(--text-muted)" }}>Ventanas:</label>
          <input
            type="number"
            min={2}
            max={24}
            value={nWindows}
            onChange={(e) => setNWindows(Math.max(2, Math.min(24, Number(e.target.value))))}
            className="w-20 text-right"
          />
          <span className="text-xs" style={{ color: "var(--text-faint)" }}>
            (entre 2 y 24)
          </span>
        </div>
        <button onClick={run} disabled={running || !strategyId} className="btn-primary inline-flex items-center gap-2">
          {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
          {running ? "Corriendo..." : "Walk-forward"}
        </button>
      </div>

      {data && (
        <>
          <div className="card p-5 mb-4">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <Metric label="Consistencia" value={`${data.summary.consistency_pct}%`} hint={`${data.summary.n_profitable}/${data.summary.n_windows} ventanas en verde`} tone={data.summary.consistency_pct >= 80 ? "green" : data.summary.consistency_pct >= 50 ? "neutral" : "red"} />
              <Metric label="PnL agregado" value={formatCurrency(data.summary.total_pnl_aggregated)} tone={data.summary.total_pnl_aggregated >= 0 ? "green" : "red"} />
              <Metric label="Promedio/ventana" value={formatCurrency(data.summary.avg_pnl_per_window)} />
              <Metric label="Mejor ventana" value={formatCurrency(data.summary.best_window_pnl)} tone="green" />
              <Metric label="Peor ventana" value={formatCurrency(data.summary.worst_window_pnl)} tone={data.summary.worst_window_pnl >= 0 ? "green" : "red"} />
            </div>
          </div>

          <div className="card p-5 mb-4">
            <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--text)" }}>PnL por ventana</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={data.windows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="index" stroke="var(--text-faint)" fontSize={11} tickLine={false} axisLine={false} tickFormatter={(i) => `W${i}`} />
                <YAxis stroke="var(--text-faint)" fontSize={11} tickLine={false} axisLine={false} width={60} tickFormatter={(v) => `$${v.toLocaleString()}`} />
                <Tooltip
                  cursor={{ fill: "var(--bg-hover)" }}
                  contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                  formatter={(v) => [formatCurrency(typeof v === "number" ? v : Number(v ?? 0)), "PnL"]}
                />
                <Bar dataKey="total_pnl">
                  {data.windows.map((w, i) => (
                    <Cell key={i} fill={w.total_pnl >= 0 ? "var(--green)" : "var(--red)"} fillOpacity={0.75} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="card p-5">
            <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--text)" }}>Detalle por ventana</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead style={{ color: "var(--text-faint)" }}>
                  <tr>
                    <th className="text-left py-2 text-xs uppercase tracking-wider pr-4">Ventana</th>
                    <th className="text-right py-2 text-xs uppercase tracking-wider pr-4">Periodo</th>
                    <th className="text-right py-2 text-xs uppercase tracking-wider pr-4">Trades</th>
                    <th className="text-right py-2 text-xs uppercase tracking-wider pr-4">WR</th>
                    <th className="text-right py-2 text-xs uppercase tracking-wider pr-4">PnL</th>
                    <th className="text-right py-2 text-xs uppercase tracking-wider pr-4">Sharpe</th>
                    <th className="text-right py-2 text-xs uppercase tracking-wider">DD</th>
                  </tr>
                </thead>
                <tbody>
                  {data.windows.map((w) => (
                    <tr key={w.index} className="border-t" style={{ borderColor: "var(--border)" }}>
                      <td className="py-2 pr-4" style={{ color: "var(--text)" }}>W{w.index}</td>
                      <td className="py-2 pr-4 text-right text-xs" style={{ color: "var(--text-muted)" }}>
                        {new Date(w.period_start).toLocaleDateString("es-CO", { month: "short", day: "numeric" })} → {new Date(w.period_end).toLocaleDateString("es-CO", { month: "short", day: "numeric" })}
                      </td>
                      <td className="py-2 pr-4 text-right tabular-nums" style={{ color: "var(--text-muted)" }}>{w.n_trades}</td>
                      <td className="py-2 pr-4 text-right tabular-nums" style={{ color: w.win_rate_pct >= 55 ? "var(--green)" : "var(--text)" }}>{w.win_rate_pct.toFixed(1)}%</td>
                      <td className="py-2 pr-4 text-right tabular-nums font-medium" style={{ color: w.total_pnl >= 0 ? "var(--green)" : "var(--red)" }}>
                        {w.total_pnl >= 0 ? "+" : ""}{formatCurrency(w.total_pnl)}
                      </td>
                      <td className="py-2 pr-4 text-right tabular-nums" style={{ color: "var(--text-muted)" }}>{w.sharpe.toFixed(2)}</td>
                      <td className="py-2 text-right tabular-nums" style={{ color: "var(--red)" }}>{w.max_drawdown_pct.toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
function GridSearchPanel({ strategyId, period, toast }: { strategyId: string; period: PeriodRange; toast: ReturnType<typeof useToast> }) {
  const [thresholds, setThresholds] = useState("0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50");
  const [minVolume, setMinVolume] = useState("0, 1000, 5000");
  const [running, setRunning] = useState(false);
  const [data, setData] = useState<{ results: GridResult[]; best: GridResult; param_names: string[] } | null>(null);

  async function run() {
    if (!strategyId) return;
    setRunning(true);
    try {
      const grid: Record<string, number[]> = {};
      const tArr = thresholds.split(",").map((x) => parseFloat(x.trim())).filter((x) => !isNaN(x));
      if (tArr.length) grid.threshold = tArr;
      const vArr = minVolume.split(",").map((x) => parseFloat(x.trim())).filter((x) => !isNaN(x));
      if (vArr.length) grid.min_volume_usd = vArr;

      const res = await fetch(`${getApiBase()}/api/advanced/grid-search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy_id: strategyId, period_start: period.start, period_end: period.end, grid, max_combinations: 100 }),
      });
      if (!res.ok) throw new Error(await res.text());
      const j = await res.json();
      setData(j);
      toast.push(`${j.results.length} combinaciones probadas. Mejor Sharpe: ${j.best.sharpe.toFixed(2)}`, "success");
    } catch (e) {
      toast.push(`Error: ${String(e)}`, "error");
    } finally {
      setRunning(false);
    }
  }

  return (
    <>
      <div className="card p-4 mb-4">
        <div className="grid md:grid-cols-2 gap-3 mb-3">
          <div>
            <label className="text-xs uppercase tracking-wider block mb-1.5" style={{ color: "var(--text-muted)" }}>
              Thresholds a probar (separados por coma, 0.0 a 1.0)
            </label>
            <input type="text" value={thresholds} onChange={(e) => setThresholds(e.target.value)} className="w-full" />
          </div>
          <div>
            <label className="text-xs uppercase tracking-wider block mb-1.5" style={{ color: "var(--text-muted)" }}>
              Volumen mínimo USD (separados por coma)
            </label>
            <input type="text" value={minVolume} onChange={(e) => setMinVolume(e.target.value)} className="w-full" />
          </div>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs" style={{ color: "var(--text-faint)" }}>
            Total combinaciones: {(thresholds.split(",").length) * (minVolume.split(",").length)}
          </span>
          <button onClick={run} disabled={running || !strategyId} className="btn-primary inline-flex items-center gap-2">
            {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            {running ? "Corriendo..." : "Grid search"}
          </button>
        </div>
      </div>

      {data && (
        <>
          <div className="card p-5 mb-4" style={{ background: "var(--green-light)", borderColor: "var(--green)" }}>
            <div className="text-xs uppercase tracking-wider mb-2" style={{ color: "var(--green)" }}>
              🏆 Mejor combinación (max Sharpe)
            </div>
            <div className="flex flex-wrap gap-6">
              <div>
                <div className="text-xs" style={{ color: "var(--text-faint)" }}>Parámetros</div>
                <div className="font-mono text-sm" style={{ color: "var(--text)" }}>
                  {JSON.stringify(data.best.params)}
                </div>
              </div>
              <Metric label="Sharpe" value={data.best.sharpe.toFixed(2)} tone="green" />
              <Metric label="WR" value={`${data.best.win_rate_pct.toFixed(1)}%`} />
              <Metric label="PnL" value={formatCurrency(data.best.total_pnl)} tone="green" />
              <Metric label="Trades" value={data.best.n_trades.toLocaleString()} />
              <Metric label="Max DD" value={`${data.best.max_drawdown_pct.toFixed(1)}%`} tone="red" />
            </div>
          </div>

          <div className="card p-5">
            <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--text)" }}>
              Todas las combinaciones (ordenadas por Sharpe)
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead style={{ color: "var(--text-faint)" }}>
                  <tr>
                    <th className="text-left py-2 text-xs uppercase tracking-wider pr-4">Parámetros</th>
                    <th className="text-right py-2 text-xs uppercase tracking-wider pr-4">Trades</th>
                    <th className="text-right py-2 text-xs uppercase tracking-wider pr-4">WR</th>
                    <th className="text-right py-2 text-xs uppercase tracking-wider pr-4">PnL</th>
                    <th className="text-right py-2 text-xs uppercase tracking-wider pr-4">Sharpe</th>
                    <th className="text-right py-2 text-xs uppercase tracking-wider pr-4">DD</th>
                    <th className="text-right py-2 text-xs uppercase tracking-wider">PF</th>
                  </tr>
                </thead>
                <tbody>
                  {data.results.map((r, i) => (
                    <tr key={i} className="border-t hover:bg-opacity-50" style={{ borderColor: "var(--border)" }}>
                      <td className="py-2 pr-4 font-mono text-xs" style={{ color: "var(--text)" }}>
                        {Object.entries(r.params).map(([k, v]) => `${k}=${v}`).join(" · ")}
                      </td>
                      <td className="py-2 pr-4 text-right tabular-nums" style={{ color: "var(--text-muted)" }}>{r.n_trades}</td>
                      <td className="py-2 pr-4 text-right tabular-nums" style={{ color: r.win_rate_pct >= 55 ? "var(--green)" : "var(--text)" }}>{r.win_rate_pct.toFixed(1)}%</td>
                      <td className="py-2 pr-4 text-right tabular-nums font-medium" style={{ color: r.total_pnl >= 0 ? "var(--green)" : "var(--red)" }}>
                        {r.total_pnl >= 0 ? "+" : ""}{formatCurrency(r.total_pnl)}
                      </td>
                      <td className="py-2 pr-4 text-right tabular-nums" style={{ color: r.sharpe >= 2 ? "var(--green)" : "var(--text-muted)" }}>{r.sharpe.toFixed(2)}</td>
                      <td className="py-2 pr-4 text-right tabular-nums" style={{ color: "var(--red)" }}>{r.max_drawdown_pct.toFixed(1)}%</td>
                      <td className="py-2 text-right tabular-nums" style={{ color: "var(--text-muted)" }}>{r.profit_factor !== null ? r.profit_factor.toFixed(2) : "∞"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </>
  );
}

function Metric({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: "green" | "red" | "neutral" }) {
  const color = tone === "green" ? "var(--green)" : tone === "red" ? "var(--red)" : "var(--text)";
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider mb-1" style={{ color: "var(--text-faint)" }}>
        {label}
      </div>
      <div className="text-base font-semibold tabular-nums" style={{ color }}>
        {value}
      </div>
      {hint && <div className="text-[10px] mt-0.5" style={{ color: "var(--text-muted)" }}>{hint}</div>}
    </div>
  );
}

export default function LabPage() {
  return (
    <Suspense fallback={<div className="p-8" style={{ color: "var(--text-muted)" }}>Cargando lab…</div>}>
      <LabPageInner />
    </Suspense>
  );
}
