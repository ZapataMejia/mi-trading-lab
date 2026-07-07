"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, PanelLeftClose, PanelLeftOpen, Play, TrendingUp, Upload } from "lucide-react";
import { EquityChart } from "@/components/EquityChart";
import { MetricsGrid } from "@/components/MetricsGrid";
import { TradesTable } from "@/components/TradesTable";
import { useToast } from "@/components/Toast";
import { formatCurrency } from "@/lib/api";
import type { BacktestResult, EquityPoint, Trade } from "@/lib/types";

import { getApiBase } from "@/lib/api-base";
import { fetchErrorMessage, waitForBackend } from "@/lib/fetch-error";
import { useCapabilities } from "@/components/CapabilitiesProvider";

const MAX_SIM_DAYS_ONLINE = 90;
const MAX_SIM_DAYS_LOCAL = 400;
const FETCH_TIMEOUT_MS = 55000;

interface FondeoParams {
  fast_period: number;
  slow_period: number;
  risk_pct: number;
  tp_ratio: number;
  sess_start: number;
  sess_end: number;
  max_trades_per_day: number;
  initial_balance: number;
  mm_risk_pct: number;
  slippage_pips: number;
  broker_utc_offset_hours: number;
  allow_long: boolean;
  allow_short: boolean;
  period_start: string;
  period_end: string;
}

const DEFAULTS: FondeoParams = {
  fast_period: 9,
  slow_period: 18,
  risk_pct: 2.1,
  tp_ratio: 1.0,
  sess_start: 700,
  sess_end: 1100,
  max_trades_per_day: 2,
  initial_balance: 5000,
  mm_risk_pct: 2.1,
  slippage_pips: 2,
  broker_utc_offset_hours: 7,
  allow_long: true,
  allow_short: true,
  period_start: "2026-01-01",
  period_end: "2026-03-31",
};

function periodDays(start: string, end: string): number {
  const s = new Date(start + "T00:00:00");
  const e = new Date(end + "T00:00:00");
  return Math.max(1, Math.round((e.getTime() - s.getTime()) / 86400000) + 1);
}

interface WsEval {
  plan: string;
  phase: number;
  meta_usd: number;
  static_dd_pct: number;
  max_daily_loss_pct: number;
  trading_days: number;
  days_to_meta: number | null;
  summary: string;
  checks: Record<string, boolean>;
}

interface HedgedSim {
  outcome: string;
  winner: string | null;
  days_to_win: number | null;
  summary: string;
  account_a: { label: string; total_pnl: number; total_pnl_pct: number; n_trades: number; ws_eval: WsEval };
  account_b: { label: string; total_pnl: number; total_pnl_pct: number; n_trades: number; ws_eval: WsEval };
  windows?: {
    "7d": HedgedWindowRow;
    "14d": HedgedWindowRow;
    "30d": HedgedWindowRow;
  };
}

interface HedgedWindowRow {
  pass_rate_pct: number;
  pair_wins: number;
  attempts: number;
  median_days: number | null;
}

interface HedgedReport {
  bars: number;
  windows: Record<string, HedgedWindowRow & { a_wins?: number; b_wins?: number; both_fail?: number }>;
  full_period?: {
    account_a_pnl: number;
    account_b_pnl: number;
    account_a_dd: number;
    account_b_dd: number;
  };
  verdict?: string;
}

interface WsWindowSim {
  windows: {
    "14d": { pass_rate_pct: number; passed: number; attempts: number; median_days_to_meta: number | null };
    "30d": { pass_rate_pct: number; passed: number; attempts: number; median_days_to_meta: number | null };
  };
}

function hhmmLabel(v: number) {
  const h = Math.floor(v / 100);
  const m = v % 100;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export default function FondeoPage() {
  const [params, setParams] = useState<FondeoParams>(DEFAULTS);
  const [running, setRunning] = useState(false);
  const [simError, setSimError] = useState<string | null>(null);
  const [showParams, setShowParams] = useState(true);
  const [result, setResult] = useState<(BacktestResult & { by_year?: YearRow[]; bars_used?: number; data_source?: string; ws_eval?: WsEval }) | null>(null);
  const [windowSim, setWindowSim] = useState<WsWindowSim | null>(null);
  const [hedgeSim, setHedgeSim] = useState<HedgedSim | null>(null);
  const [simRunning, setSimRunning] = useState(false);
  const [hedgeReport, setHedgeReport] = useState<HedgedReport | null>(null);
  const [hedgeRunning, setHedgeRunning] = useState(false);
  const [dataInfo, setDataInfo] = useState<string>("");
  const [dataRange, setDataRange] = useState<{ date_from: string; date_to: string; rows: number } | null>(null);
  const toast = useToast();
  const caps = useCapabilities();
  const abortRef = useRef<AbortController | null>(null);
  const runInFlight = useRef(false);
  const isCloud =
    caps.online_mode ||
    getApiBase().includes("pythonanywhere.com") ||
    (typeof window !== "undefined" && window.location.hostname.includes("vercel.app"));
  const maxSimDays = caps.max_sim_days > 0 ? caps.max_sim_days : MAX_SIM_DAYS_LOCAL;
  const shortPeriodOnly = maxSimDays <= 90;
  const selectedDays = periodDays(params.period_start, params.period_end);
  const periodTooLong = selectedDays > maxSimDays;

  useEffect(() => {
    fetch(`${getApiBase()}/api/fondeo/data-range?symbol=EURUSD&timeframe=M5`)
      .then((r) => r.json())
      .then((j) => {
        if (j.available && j.date_from && j.date_to) {
          setDataRange({ date_from: j.date_from, date_to: j.date_to, rows: j.rows });
          setDataInfo(`EURUSD M5 · ${j.rows?.toLocaleString()} velas · ${j.date_from} → ${j.date_to}`);
        } else {
          setDataRange(null);
          setDataInfo("Sin datos M5 en el servidor");
        }
      })
      .catch(() => setDataInfo("Backend no disponible"));
  }, []);

  function datesOk(p: FondeoParams): boolean {
    if (!dataRange) return true;
    if (p.period_start > p.period_end) return false;
    return p.period_start <= dataRange.date_to && p.period_end >= dataRange.date_from;
  }

  const datesOutOfRange = dataRange && !datesOk(params);

  const runBacktest = useCallback(async (p: FondeoParams) => {
    if (runInFlight.current) return;
    if (dataRange && !datesOk(p)) {
      toast.push(
        `Fechas fuera de rango. Datos disponibles: ${dataRange.date_from} → ${dataRange.date_to}`,
        "error",
      );
      return;
    }
    const days = periodDays(p.period_start, p.period_end);
    if (days > maxSimDays) {
      const msg = `Periodo demasiado largo (${days} días). Máximo ${maxSimDays} días por simulación${
        shortPeriodOnly && isCloud ? " en la versión en línea" : ""
      }. Prueba un rango más corto.`;
      setSimError(msg);
      toast.push(msg, "error");
      return;
    }
    runInFlight.current = true;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    setRunning(true);
    setSimError(null);
    try {
      const apiBase = getApiBase();
      const awake = await waitForBackend(apiBase);
      if (!awake) throw new Error("Failed to fetch");

      const body: Record<string, unknown> = { ...p, symbol: "EURUSD", timeframe: "M5" };
      if (!p.period_start) delete body.period_start;
      if (!p.period_end) delete body.period_end;

      const res = await fetch(`${apiBase}/api/fondeo/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(await res.text());
      const j = await res.json();
      setResult(j);
      setWindowSim(null);
    } catch (e) {
      const msg = fetchErrorMessage(e);
      setSimError(msg);
      toast.push(msg, "error");
    } finally {
      clearTimeout(timeout);
      runInFlight.current = false;
      setRunning(false);
    }
  }, [dataRange, isCloud, maxSimDays, shortPeriodOnly, toast]);

  const runWindowSim = useCallback(async () => {
    setSimRunning(true);
    try {
      const body: Record<string, unknown> = { ...params, symbol: "EURUSD", timeframe: "M5" };
      const res = await fetch(`${getApiBase()}/api/fondeo/ws-eval-sim`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await res.text());
      setWindowSim(await res.json());
    } catch (e) {
      toast.push(`Sim eval: ${String(e)}`, "error");
    } finally {
      setSimRunning(false);
    }
  }, [params, toast]);

  const runHedgeSim = useCallback(async () => {
    setHedgeRunning(true);
    try {
      const body: Record<string, unknown> = { ...params, symbol: "EURUSD", timeframe: "M5", commission_usd: 5 };
      const [simRes, labRes] = await Promise.all([
        fetch(`${getApiBase()}/api/fondeo/hedge-sim`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }),
        fetch(`${getApiBase()}/api/fondeo/hedge-lab-run`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }),
      ]);
      if (!simRes.ok) throw new Error(await simRes.text());
      if (!labRes.ok) throw new Error(await labRes.text());
      setHedgeSim(await simRes.json());
      setHedgeReport(await labRes.json());
      toast.push("Backtest hedge completo", "success");
    } catch (e) {
      toast.push(`Hedge sim: ${String(e)}`, "error");
    } finally {
      setHedgeRunning(false);
    }
  }, [params, toast]);

  function set<K extends keyof FondeoParams>(key: K, value: FondeoParams[K]) {
    setParams((prev) => ({ ...prev, [key]: value }));
  }

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await fetch(`${getApiBase()}/api/fondeo/upload-csv?symbol=EURUSD&timeframe=M5`, {
        method: "POST",
        body: fd,
      });
      if (!res.ok) throw new Error(await res.text());
      const j = await res.json();
      toast.push(`CSV cargado: ${j.rows.toLocaleString()} barras`, "success");
      setDataInfo(`EURUSD_M5.csv (${j.rows.toLocaleString()} barras)`);
      runBacktest(params);
    } catch (err) {
      toast.push(`Upload falló: ${String(err)}`, "error");
    }
    e.target.value = "";
  }

  const trades = (result?.trades ?? []) as Trade[];
  const equity = (result?.equity_curve ?? []) as EquityPoint[];

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <header className="mb-6 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight inline-flex items-center gap-2" style={{ color: "var(--text)" }}>
            <TrendingUp size={22} strokeWidth={1.75} />
            Curso · EMA Cross (HobbyCode)
          </h1>
          <p className="text-sm mt-2 max-w-2xl" style={{ color: "var(--text-muted)" }}>
            Estrategia del <strong>Programa de Mentorías para Traders Algorítmicos</strong> (AlgoWizard / HobbyCode):
            cruce de medias EMA 9 y 18 en EURUSD M5, sesión Londres, riesgo ~2,1% y TP 1:1.
          </p>
          <p className="text-sm mt-2 max-w-2xl" style={{ color: "var(--text-muted)" }}>
            Para fondeo WS recomiendan <strong>dos cuentas de $5,000</strong>: una sigue la señal normal y la otra
            hace lo contrario (hedge). Si una pasa la eval (+8%), la otra pierde — abajo puedes simular ese par.
          </p>
          <p className="text-xs mt-2" style={{ color: "var(--text-faint)" }}>
            Datos: {dataInfo}
            {" · "}
            <Link href="/fondeo/liquidity-sweep" className="underline" style={{ color: "var(--accent)" }}>
              Ir al simulador Liquidity Sweep →
            </Link>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="btn-secondary inline-flex items-center gap-2 cursor-pointer text-sm">
            <Upload size={14} />
            Subir CSV M5
            <input type="file" accept=".csv" className="hidden" onChange={onUpload} />
          </label>
          <button
            onClick={() => runBacktest(params)}
            disabled={running || periodTooLong || !!datesOutOfRange}
            className="btn-primary inline-flex items-center gap-2"
          >
            {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            {running ? "Corriendo..." : "Correr"}
          </button>
        </div>
      </header>

      <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
        <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-faint)" }}>
          Parámetros EMA
        </p>
        <button
          type="button"
          className="btn-secondary text-xs inline-flex items-center gap-1.5"
          onClick={() => setShowParams((v) => !v)}
        >
          {showParams ? <PanelLeftClose size={14} /> : <PanelLeftOpen size={14} />}
          {showParams ? "Ocultar panel" : "Mostrar panel"}
        </button>
      </div>

      <div className={`grid gap-4 ${showParams ? "lg:grid-cols-[320px_1fr]" : "grid-cols-1"}`}>
        {showParams && (
        <aside className="card p-4 space-y-4">
          <Section title="EMAs">
            <Slider label="Rápida" value={params.fast_period} min={2} max={50} step={1} onChange={(v) => set("fast_period", v)} />
            <Slider label="Lenta" value={params.slow_period} min={3} max={100} step={1} onChange={(v) => set("slow_period", v)} />
          </Section>

          <Section title="Riesgo / SL-TP">
            <Slider label="Risk % (SL distancia)" value={params.risk_pct} min={0.5} max={6} step={0.1} onChange={(v) => set("risk_pct", v)} suffix="%" />
            <Slider label="TP ratio (1:1)" value={params.tp_ratio} min={0.5} max={3} step={0.1} onChange={(v) => set("tp_ratio", v)} />
            <Slider label="MM riesgo % balance" value={params.mm_risk_pct} min={0.5} max={6} step={0.1} onChange={(v) => set("mm_risk_pct", v)} suffix="%" />
            <Slider label="Slippage" value={params.slippage_pips} min={0} max={10} step={0.5} onChange={(v) => set("slippage_pips", v)} suffix=" pips" />
          </Section>

          <Section title="Sesión (hora broker)">
            <Slider label="Offset UTC → broker" value={params.broker_utc_offset_hours} min={-12} max={12} step={1} onChange={(v) => set("broker_utc_offset_hours", v)} suffix=" h" />
            <Slider label="Inicio" value={params.sess_start} min={0} max={2359} step={5} onChange={(v) => set("sess_start", v)} format={hhmmLabel} />
            <Slider label="Fin" value={params.sess_end} min={0} max={2359} step={5} onChange={(v) => set("sess_end", v)} format={hhmmLabel} />
            <Slider label="Max trades/día" value={params.max_trades_per_day} min={1} max={5} step={1} onChange={(v) => set("max_trades_per_day", v)} />
          </Section>

          <Section title="Cuenta / fechas">
            <Slider label="Capital inicial" value={params.initial_balance} min={1000} max={50000} step={500} onChange={(v) => set("initial_balance", v)} prefix="$" />
            <div className="grid grid-cols-2 gap-2">
              <DateField label="Desde" value={params.period_start} onChange={(v) => set("period_start", v)} />
              <DateField label="Hasta" value={params.period_end} onChange={(v) => set("period_end", v)} />
            </div>
            <p className="text-xs" style={{ color: periodTooLong ? "var(--red)" : "var(--text-faint)" }}>
              Periodo: {selectedDays} días
              {shortPeriodOnly && isCloud && ` · máx. ${maxSimDays} en la nube`}
            </p>
            {periodTooLong && (
              <p className="text-xs" style={{ color: "var(--red)" }}>
                Acorta las fechas (ej. Ene–Mar 2026). Periodos largos solo en la versión local.
              </p>
            )}
            {datesOutOfRange && dataRange && (
              <p className="text-xs" style={{ color: "var(--red)" }}>
                Fuera de rango · datos {dataRange.date_from} → {dataRange.date_to}
              </p>
            )}
          </Section>

          <Section title="Dirección">
            <Toggle label="Long" checked={params.allow_long} onChange={(v) => set("allow_long", v)} />
            <Toggle label="Short" checked={params.allow_short} onChange={(v) => set("allow_short", v)} />
          </Section>
        </aside>
        )}

        <main className="space-y-4 min-w-0">
          {simError && (
            <div className="card p-4 text-sm" style={{ color: "var(--red)", borderColor: "var(--red)" }}>
              {simError}
            </div>
          )}
          {result ? (
            <>
              <div className="card p-5">
                <div className="flex items-baseline justify-between mb-4 flex-wrap gap-2">
                  <div>
                    <div className="text-xs uppercase tracking-wider" style={{ color: "var(--text-faint)" }}>
                      Periodo simulado · {params.period_start} → {params.period_end}
                    </div>
                    <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                      {result.bars_used?.toLocaleString()} barras · {trades.length} operaciones · {result.duration_seconds}s
                    </p>
                    <div className="text-2xl font-semibold tabular-nums" style={{ color: result.total_pnl >= 0 ? "var(--green)" : "var(--red)" }}>
                      {result.total_pnl >= 0 ? "+" : ""}{formatCurrency(result.total_pnl)}
                      <span className="text-sm font-normal ml-2" style={{ color: "var(--text-muted)" }}>
                        ({result.total_pnl_pct >= 0 ? "+" : ""}{result.total_pnl_pct}%)
                      </span>
                    </div>
                  </div>
                  <div className="text-xs font-mono" style={{ color: "var(--text-faint)" }}>
                    Max DD {result.metrics.max_drawdown_pct.toFixed(1)}% · PF {result.metrics.profit_factor?.toFixed(2)}
                  </div>
                </div>
                <MetricsGrid
                  metrics={result.metrics}
                  initialBankroll={result.initial_bankroll}
                  finalBankroll={result.final_bankroll}
                  totalPnl={result.total_pnl}
                  totalPnlPct={result.total_pnl_pct}
                  durationSeconds={result.duration_seconds}
                />
              </div>

              {result.ws_eval && (
                <div className="card p-4">
                  <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
                    <h3 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
                      Eval WS CLASSIC $5k — fase 1
                    </h3>
                    <button
                      onClick={runWindowSim}
                      disabled={simRunning}
                      className="btn-secondary text-xs px-3 py-1.5"
                    >
                      {simRunning ? "Simulando..." : "Simular ventanas 14/30 días"}
                    </button>
                  </div>
                  <p className="text-sm mb-3" style={{ color: result.ws_eval.checks.pass_all ? "var(--green)" : "var(--red)" }}>
                    {result.ws_eval.summary}
                  </p>
                  <div className="grid sm:grid-cols-2 gap-2 text-xs">
                    {[
                      ["Meta +8% ($400)", result.ws_eval.checks.pass_meta],
                      ["DD estático ≤ 8%", result.ws_eval.checks.pass_static_dd],
                      ["DD diario ≤ 5%", result.ws_eval.checks.pass_daily_dd],
                      ["Mín. 4 días trading", result.ws_eval.checks.pass_min_days],
                      ["PF ≥ 1", result.ws_eval.checks.pass_pf],
                      ["Riesgo ≤ 2.1%", result.ws_eval.checks.pass_risk],
                    ].map(([label, ok]) => (
                      <div key={label as string} className="flex justify-between px-2 py-1 rounded" style={{ background: "var(--bg-hover)" }}>
                        <span style={{ color: "var(--text-muted)" }}>{label}</span>
                        <span style={{ color: ok ? "var(--green)" : "var(--red)" }}>{ok ? "✓" : "✗"}</span>
                      </div>
                    ))}
                  </div>
                  <p className="text-xs mt-2" style={{ color: "var(--text-faint)" }}>
                    DD {result.ws_eval.static_dd_pct}% · DD día max {result.ws_eval.max_daily_loss_pct}% ·
                    {result.ws_eval.trading_days} días con trades
                    {result.ws_eval.days_to_meta != null && ` · meta en ${result.ws_eval.days_to_meta}d`}
                  </p>
                  {windowSim && (
                    <div className="mt-3 pt-3 border-t text-xs grid sm:grid-cols-2 gap-2" style={{ borderColor: "var(--border)" }}>
                      <div>
                        <strong>14 días:</strong> {windowSim.windows["14d"].passed}/{windowSim.windows["14d"].attempts} ({windowSim.windows["14d"].pass_rate_pct}%)
                        {windowSim.windows["14d"].median_days_to_meta != null && ` · med ${windowSim.windows["14d"].median_days_to_meta}d a meta`}
                      </div>
                      <div>
                        <strong>30 días:</strong> {windowSim.windows["30d"].passed}/{windowSim.windows["30d"].attempts} ({windowSim.windows["30d"].pass_rate_pct}%)
                      </div>
                    </div>
                  )}
                </div>
              )}

              <div className="card p-4 border-2" style={{ borderColor: "var(--accent, #6366f1)" }}>
                <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
                  <div>
                    <h3 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
                      Hedge 2 cuentas $5k (recomendación del curso)
                    </h3>
                    <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                      Cuenta A = señal del cruce EMA · Cuenta B = operación contraria · meta +8% en una eval WS
                    </p>
                  </div>
                  <button
                    onClick={runHedgeSim}
                    disabled={hedgeRunning}
                    className="btn-primary text-xs px-3 py-1.5"
                  >
                    {hedgeRunning ? "Backtesteando..." : "Backtest hedge completo"}
                  </button>
                </div>
                {hedgeSim ? (
                  <>
                    <p className="text-sm mb-3 font-medium" style={{ color: hedgeSim.outcome.includes("wins") ? "var(--green)" : "var(--red)" }}>
                      {hedgeSim.summary}
                      {hedgeSim.days_to_win != null && ` · ${hedgeSim.days_to_win} días`}
                    </p>
                    <div className="grid sm:grid-cols-2 gap-3 text-xs">
                      {[hedgeSim.account_a, hedgeSim.account_b].map((acc) => (
                        <div key={acc.label} className="p-3 rounded" style={{ background: "var(--bg-hover)" }}>
                          <div className="font-medium mb-1" style={{ color: "var(--text)" }}>{acc.label}</div>
                          <div style={{ color: acc.total_pnl >= 0 ? "var(--green)" : "var(--red)" }}>
                            {acc.total_pnl >= 0 ? "+" : ""}{formatCurrency(acc.total_pnl)} ({acc.total_pnl_pct}%)
                          </div>
                          <div style={{ color: "var(--text-muted)" }}>
                            {acc.n_trades} trades · DD {acc.ws_eval.static_dd_pct}% · {acc.ws_eval.summary}
                          </div>
                        </div>
                      ))}
                    </div>
                    {hedgeSim.windows && (
                      <div className="mt-3 pt-3 border-t text-xs grid sm:grid-cols-3 gap-2" style={{ borderColor: "var(--border)" }}>
                        {(["7d", "14d", "30d"] as const).map((k) => (
                          <div key={k}>
                            <strong>{k}:</strong> {hedgeSim.windows![k].pair_wins}/{hedgeSim.windows![k].attempts} ({hedgeSim.windows![k].pass_rate_pct}%)
                            {hedgeSim.windows![k].median_days != null && ` · med ${hedgeSim.windows![k].median_days}d`}
                          </div>
                        ))}
                      </div>
                    )}
                    {hedgeReport && (
                      <div className="mt-3 pt-3 border-t text-xs space-y-2" style={{ borderColor: "var(--border)" }}>
                        <div className="font-medium" style={{ color: "var(--text)" }}>
                          Reporte lab — {hedgeReport.bars.toLocaleString()} barras
                        </div>
                        <div className="grid sm:grid-cols-4 gap-2">
                          {(["7d", "14d", "30d", "60d"] as const).map((k) => {
                            const w = hedgeReport.windows[k];
                            if (!w) return null;
                            return (
                              <div key={k} className="px-2 py-1 rounded" style={{ background: "var(--bg-hover)" }}>
                                <strong>{k}:</strong> {w.pair_wins}/{w.attempts} ({w.pass_rate_pct}%)
                              </div>
                            );
                          })}
                        </div>
                        {hedgeReport.full_period && (
                          <div style={{ color: "var(--text-muted)" }}>
                            Periodo seleccionado (referencia): A {formatCurrency(hedgeReport.full_period.account_a_pnl)} · B {formatCurrency(hedgeReport.full_period.account_b_pnl)}
                          </div>
                        )}
                      </div>
                    )}
                  </>
                ) : (
                  <p className="text-xs" style={{ color: "var(--text-faint)" }}>
                    Pulsa para simular el par. Para imitar <strong>1 eval</strong>, acota fechas a ~30–60 días (no 5 años).
                    En vivo el copiador para al +8% equity aunque el trade no cierre TP.
                  </p>
                )}
              </div>

              <div className="card p-5">
                <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--text)" }}>Equity</h3>
                <EquityChart data={equity} initialBankroll={result.initial_bankroll} />
              </div>

              <div className="card p-5">
                <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--text)" }}>
                  Trades ({trades.length})
                </h3>
                <TradesTable trades={trades.slice().reverse()} marketType="forex" />
              </div>
            </>
          ) : (
            <div className="card p-12 text-center text-sm" style={{ color: "var(--text-faint)" }}>
              {running
                ? "Calculando backtest… (~10–30 s en la nube)"
                : "Elige fechas (máx. 90 días en la nube) y pulsa Correr para simular el cruce EMA."}
            </div>
          )}
        </main>
      </div>

      <div className="mt-6 card p-4 text-xs" style={{ color: "var(--text-muted)" }}>
        <strong style={{ color: "var(--text)" }}>Eval WS CLASSIC $5k:</strong> meta +8% ($400) · DD estático 8% · DD diario 5% · mín. 4 días trading · riesgo ≤2.1% · max 2 trades/día · sin límite de tiempo (inactividad 30d).
        {" "}Defaults = curso (9/20, sesión 8–10, hedged 2 cuentas). Ver <code>sqx/HEDGED_EVAL_CHECKLIST.md</code>.
        {" "}En la nube usa periodos cortos (≤90 días). Para años completos, prueba mes a mes en el Simulador WS.
      </div>
    </div>
  );
}

interface YearRow {
  year: string;
  trades: number;
  wins: number;
  win_rate_pct: number;
  pnl: number;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-xs uppercase tracking-wider mb-2" style={{ color: "var(--text-faint)" }}>{title}</h3>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  onChange,
  suffix = "",
  prefix = "",
  format,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  suffix?: string;
  prefix?: string;
  format?: (v: number) => string;
}) {
  const display = format ? format(value) : `${prefix}${value}${suffix}`;
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span style={{ color: "var(--text-muted)" }}>{label}</span>
        <span className="tabular-nums font-medium" style={{ color: "var(--text)" }}>{display}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full"
      />
    </div>
  );
}

function DateField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <label className="text-xs block mb-1" style={{ color: "var(--text-muted)" }}>{label}</label>
      <input type="date" value={value} onChange={(e) => onChange(e.target.value)} className="w-full text-sm" />
    </div>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: "var(--text)" }}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}
