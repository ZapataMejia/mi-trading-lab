"use client";

import { useEffect, useMemo, useState, use } from "react";
import Link from "next/link";
import { ChevronLeft, Play, Loader2, Download, GitCompare } from "lucide-react";
import { api } from "@/lib/api";
import type { BacktestResult, Strategy, StrategyConfig } from "@/lib/types";
import { EquityChart } from "@/components/EquityChart";
import { MetricsGrid } from "@/components/MetricsGrid";
import { TradesTable } from "@/components/TradesTable";
import { PeriodSelector, type PeriodRange } from "@/components/PeriodSelector";
import { ConfigEditor } from "@/components/ConfigEditor";
import { BreakdownPanel } from "@/components/BreakdownPanel";
import { useToast } from "@/components/Toast";
import { useCapabilities } from "@/components/CapabilitiesProvider";
import { marketBacktestAvailable } from "@/lib/capabilities";

export default function StrategyDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const decoded = decodeURIComponent(id);
  const toast = useToast();
  const caps = useCapabilities();

  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"overview" | "trades" | "config" | "breakdowns">("overview");

  const [period, setPeriod] = useState<PeriodRange>(() => {
    if (typeof window !== "undefined") {
      const saved = sessionStorage.getItem(`period:${decoded}`);
      if (saved) try { return JSON.parse(saved); } catch {}
    }
    return { preset: "1y" };
  });

  const [editedConfig, setEditedConfig] = useState<StrategyConfig>({});
  const [breakdownTrigger, setBreakdownTrigger] = useState(0);

  // Persistir período
  useEffect(() => {
    sessionStorage.setItem(`period:${decoded}`, JSON.stringify(period));
  }, [period, decoded]);

  // Cargar strategy + cualquier resultado en cache
  useEffect(() => {
    api
      .getStrategy(decoded)
      .then((s) => {
        setStrategy(s);
        setEditedConfig(s.config);
        const cached = sessionStorage.getItem(`result:${decoded}`);
        if (cached) {
          try { setResult(JSON.parse(cached)); } catch {}
        }
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [decoded]);

  const overrides = useMemo(() => {
    if (!strategy) return undefined;
    const diff: Record<string, unknown> = {};
    for (const k of Object.keys(editedConfig)) {
      if (JSON.stringify((editedConfig as Record<string, unknown>)[k]) !== JSON.stringify((strategy.config as Record<string, unknown>)[k])) {
        diff[k] = (editedConfig as Record<string, unknown>)[k];
      }
    }
    return Object.keys(diff).length > 0 ? diff : undefined;
  }, [editedConfig, strategy]);

  async function runBacktest() {
    setRunning(true);
    setError(null);
    try {
      const r = await api.runBacktest({
        strategy_id: decoded,
        period_start: period.start,
        period_end: period.end,
        overrides,
      });
      setResult(r);
      sessionStorage.setItem(`result:${decoded}`, JSON.stringify(r));
      setBreakdownTrigger((t) => t + 1);
      toast.push(`Backtest completado: ${r.metrics.n_trades} trades, ${r.metrics.win_rate_pct.toFixed(1)}% WR`, "success");
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      toast.push(`Error: ${msg}`, "error");
    } finally {
      setRunning(false);
    }
  }

  async function exportCSV() {
    setExporting(true);
    try {
      await api.exportTrades({
        strategy_id: decoded,
        period_start: period.start,
        period_end: period.end,
        overrides,
      });
      toast.push("CSV descargado", "success");
    } catch (e) {
      toast.push(`Error al exportar: ${String(e)}`, "error");
    } finally {
      setExporting(false);
    }
  }

  if (loading) {
    return (
      <div className="p-8 max-w-6xl mx-auto">
        <div className="h-8 w-48 bg-zinc-100 animate-pulse rounded mb-3" />
        <div className="h-4 w-96 bg-zinc-100 animate-pulse rounded" />
      </div>
    );
  }

  if (!strategy) {
    return (
      <div className="p-8 max-w-6xl mx-auto">
        <div className="card p-4 text-sm" style={{ background: "var(--red-light)", borderColor: "var(--red)", color: "var(--red)" }}>
          Estrategia no encontrada: {error || decoded}
        </div>
      </div>
    );
  }

  const canBacktest = marketBacktestAvailable(caps, strategy.market_type);

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <Link href="/" className="inline-flex items-center gap-1 text-sm mb-4 hover:underline" style={{ color: "var(--text-muted)" }}>
        <ChevronLeft size={16} strokeWidth={1.75} />
        Estrategias
      </Link>

      <header className="flex items-start justify-between mb-5 gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="tag">{strategy.market_type}</span>
            {strategy.tags.map((t) => (
              <span key={t} className="tag">{t}</span>
            ))}
          </div>
          <h1 className="text-2xl font-semibold tracking-tight" style={{ color: "var(--text)" }}>
            {strategy.name}
          </h1>
          <p className="text-sm mt-1 max-w-2xl" style={{ color: "var(--text-muted)" }}>
            {strategy.description}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Link
            href={`/compare?ids=${encodeURIComponent(decoded)}`}
            className="btn-secondary inline-flex items-center gap-2"
          >
            <GitCompare size={14} strokeWidth={1.75} />
            Comparar
          </Link>
          {result && (
            <button onClick={exportCSV} disabled={exporting} className="btn-secondary inline-flex items-center gap-2">
              {exporting ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} strokeWidth={1.75} />}
              CSV
            </button>
          )}
          <button
            onClick={runBacktest}
            disabled={running || !canBacktest}
            className="btn-primary inline-flex items-center gap-2"
            title={!canBacktest ? "Backtest no disponible en este servidor" : undefined}
          >
            {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} strokeWidth={2} />}
            {running ? "Corriendo..." : result ? "Re-ejecutar" : "Correr backtest"}
          </button>
        </div>
      </header>

      {!canBacktest && (
        <div className="card p-4 mb-4 text-sm" style={{ color: "var(--text-muted)" }}>
          Esta estrategia no se puede backtestear en la versión en línea. Usa el{" "}
          <Link href="/fondeo/liquidity-sweep" className="underline" style={{ color: "var(--accent)" }}>
            Simulador WS
          </Link>{" "}
          para forex.
        </div>
      )}

      <div className="card p-3.5 mb-4">
        <PeriodSelector value={period} onChange={setPeriod} />
      </div>

      <div className="mb-6">
        <ConfigEditor
          base={strategy.config}
          current={editedConfig}
          onChange={setEditedConfig}
          onReset={() => setEditedConfig(strategy.config)}
        />
      </div>

      {error && (
        <div className="card p-4 mb-6 text-sm" style={{ background: "var(--red-light)", borderColor: "var(--red)", color: "var(--red)" }}>
          {error}
        </div>
      )}

      {!result && !running && (
        <div className="card p-8 text-center">
          <p className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>
            Selecciona un periodo arriba y dale <strong>Correr backtest</strong>.
          </p>
        </div>
      )}

      {running && (
        <div className="card p-12 text-center">
          <Loader2 size={28} strokeWidth={1.5} className="animate-spin mx-auto mb-3" style={{ color: "var(--accent)" }} />
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>Backtesteando contra el dataset historico...</p>
        </div>
      )}

      {result && (
        <>
          <section className="mb-7">
            <MetricsGrid
              metrics={result.metrics}
              finalBankroll={result.final_bankroll}
              totalPnl={result.total_pnl}
              totalPnlPct={result.total_pnl_pct}
              durationSeconds={result.duration_seconds}
            />
          </section>

          <DataCoverageNotice result={result} />

          <section className="card p-5 mb-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold" style={{ color: "var(--text)" }}>Equity curve</h3>
              <span className="text-xs" style={{ color: "var(--text-faint)" }}>
                {result.candidate_markets.toLocaleString()} mercados · {result.metrics.n_trades.toLocaleString()} ejecutados ·{" "}
                {result.skipped_markets.toLocaleString()} saltados
              </span>
            </div>
            <EquityChart data={result.equity_curve} initialBankroll={result.initial_bankroll} height={320} />
          </section>

          <section className="card p-5">
            <div className="flex items-center gap-1 mb-4 border-b" style={{ borderColor: "var(--border)" }}>
              {(["overview", "breakdowns", "trades", "config"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className="px-3 py-2 text-sm transition-colors"
                  style={{
                    color: tab === t ? "var(--text)" : "var(--text-muted)",
                    borderBottom: tab === t ? "2px solid var(--text)" : "2px solid transparent",
                    fontWeight: tab === t ? 500 : 400,
                    marginBottom: -1,
                  }}
                >
                  {t === "overview"
                    ? "Resumen"
                    : t === "breakdowns"
                    ? "Análisis"
                    : t === "trades"
                    ? `Trades (${result.trades.length})`
                    : "Config"}
                </button>
              ))}
            </div>

            {tab === "overview" && <OverviewPanel result={result} />}
            {tab === "trades" && <TradesTable trades={result.trades} />}
            {tab === "config" && <ConfigPanel config={result.config_used} strategy={strategy} />}
            {tab === "breakdowns" && (
              <BreakdownPanel
                strategyId={decoded}
                periodStart={period.start}
                periodEnd={period.end}
                overrides={overrides}
                trigger={breakdownTrigger}
              />
            )}
          </section>
        </>
      )}
    </div>
  );
}

function DataCoverageNotice({ result }: { result: BacktestResult }) {
  // El backend reporta period_end = ultimo timestamp del dataset filtrado,
  // no lo que el user pidio. Asi que comparamos contra HOY.
  const [hoyTs, setHoyTs] = useState<number | null>(null);
  useEffect(() => {
    setHoyTs(Date.now());
  }, []);
  if (hoyTs == null) return null;

  const periodEndTs = new Date(result.period_end).getTime();
  const gapDays = (hoyTs - periodEndTs) / (1000 * 60 * 60 * 24);
  if (gapDays < 2) return null;

  const lastDate = new Date(periodEndTs).toLocaleDateString("es-CO", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  return (
    <div
      className="card p-3 mb-4 text-sm flex items-start gap-2.5"
      style={{ background: "var(--amber-light)", borderColor: "var(--amber)", color: "var(--text)" }}
    >
      <span style={{ color: "var(--amber)", marginTop: 1 }}>⚠</span>
      <div>
        <div style={{ color: "var(--amber)", fontWeight: 500 }}>
          Dataset desactualizado · sin data de los últimos {Math.floor(gapDays)} días
        </div>
        <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
          Las operaciones del histórico llegan hasta <strong>{lastDate}</strong>. Para incluir los últimos días tendrías que re-correr el scraper de Polymarket que genera <code>v4_real_1y.csv</code> y <code>{`{asset}_hourly_1y_full.csv`}</code>.
        </div>
      </div>
    </div>
  );
}

function OverviewPanel({ result }: { result: BacktestResult }) {
  return (
    <div className="grid md:grid-cols-2 gap-4 text-sm">
      <div>
        <h4 className="font-medium mb-2" style={{ color: "var(--text)" }}>Período</h4>
        <p style={{ color: "var(--text-muted)" }}>
          Desde <strong suppressHydrationWarning>{new Date(result.period_start).toLocaleDateString("es-CO")}</strong> hasta{" "}
          <strong suppressHydrationWarning>{new Date(result.period_end).toLocaleDateString("es-CO")}</strong>
        </p>
      </div>
      <div>
        <h4 className="font-medium mb-2" style={{ color: "var(--text)" }}>Universo</h4>
        <p style={{ color: "var(--text-muted)" }}>
          {result.candidate_markets.toLocaleString()} mercados candidatos · {result.metrics.n_trades.toLocaleString()} ejecutados
          ({((result.metrics.n_trades / Math.max(1, result.candidate_markets)) * 100).toFixed(1)}%)
        </p>
      </div>
      {result.game_over_at && (
        <div className="md:col-span-2">
          <h4 className="font-medium mb-2" style={{ color: "var(--red)" }}>⚠ Game over</h4>
          <p style={{ color: "var(--text-muted)" }}>
            Bankroll cayó bajo el piso el <strong suppressHydrationWarning>{new Date(result.game_over_at).toLocaleDateString("es-CO")}</strong>.
          </p>
        </div>
      )}
    </div>
  );
}

function ConfigPanel({ config, strategy }: { config: Record<string, unknown>; strategy: Strategy }) {
  return (
    <div className="font-mono text-xs">
      <div className="mb-3" style={{ color: "var(--text-muted)" }}>
        <strong>ID:</strong> {strategy.id}
      </div>
      <pre className="p-4 rounded-md overflow-x-auto" style={{ background: "var(--bg-hover)", color: "var(--text)" }}>
        {JSON.stringify(config, null, 2)}
      </pre>
    </div>
  );
}
