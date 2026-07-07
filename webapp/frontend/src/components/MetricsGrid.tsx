"use client";

import type { BacktestMetrics } from "@/lib/types";
import { formatCurrency } from "@/lib/api";

export function MetricsGrid({
  metrics,
  finalBankroll,
  totalPnl,
  totalPnlPct,
  durationSeconds,
  initialBankroll,
}: {
  metrics: BacktestMetrics;
  finalBankroll: number;
  totalPnl?: number;
  totalPnlPct?: number;
  durationSeconds?: number;
  initialBankroll?: number;
}) {
  const pnl = totalPnl ?? finalBankroll - (initialBankroll ?? finalBankroll);
  const positive = pnl >= 0;
  const pnlPct = totalPnlPct ?? (initialBankroll ? ((finalBankroll - initialBankroll) / initialBankroll) * 100 : 0);

  type Tone = "green" | "red" | "neutral";
  type MetricItem = { label: string; value: string; hint?: string; tone?: Tone };

  const ROW1: MetricItem[] = [
    {
      label: "Bankroll final",
      value: formatCurrency(finalBankroll),
      tone: positive ? "green" : "red",
      hint: `${positive ? "+" : ""}${pnlPct.toFixed(1)}%`,
    },
    {
      label: "Profit total",
      value: formatCurrency(pnl),
      tone: positive ? "green" : "red",
    },
    {
      label: "Trades",
      value: metrics.n_trades.toLocaleString(),
      hint: `${metrics.n_wins}W / ${metrics.n_losses}L`,
    },
    {
      label: "Win rate",
      value: `${metrics.win_rate_pct.toFixed(1)}%`,
      tone: metrics.win_rate_pct >= 55 ? "green" : metrics.win_rate_pct < 45 ? "red" : "neutral",
    },
  ];

  const ROW2: MetricItem[] = [
    {
      label: "Sharpe",
      value: metrics.sharpe.toFixed(2),
      hint: metrics.sharpe >= 1 ? "bueno" : "bajo",
      tone: metrics.sharpe >= 1 ? "green" : "neutral",
    },
    {
      label: "Profit factor",
      value: metrics.profit_factor !== null ? metrics.profit_factor.toFixed(2) : "∞",
      tone: (metrics.profit_factor ?? 0) >= 1.2 ? "green" : "neutral",
    },
    {
      label: "Max drawdown",
      value: `${metrics.max_drawdown_pct.toFixed(1)}%`,
      tone: "red",
      hint: formatCurrency(metrics.max_drawdown_usd),
    },
    {
      label: "Expectancy",
      value: `${metrics.expectancy >= 0 ? "+" : ""}$${metrics.expectancy.toFixed(2)}`,
      tone: metrics.expectancy >= 0 ? "green" : "red",
      hint: "por trade",
    },
  ];

  const ROW3 = [
    { label: "Mejor trade", value: formatCurrency(metrics.best_trade), tone: "green" as const },
    { label: "Peor trade", value: formatCurrency(metrics.worst_trade), tone: "red" as const },
    { label: "Avg win", value: formatCurrency(metrics.avg_win), tone: "green" as const },
    { label: "Avg loss", value: formatCurrency(metrics.avg_loss), tone: "red" as const },
  ];

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {ROW1.map((m) => (
          <MetricBox key={m.label} {...m} large />
        ))}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {ROW2.map((m) => (
          <MetricBox key={m.label} {...m} />
        ))}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {ROW3.map((m) => (
          <MetricBox key={m.label} {...m} />
        ))}
      </div>
      <div className="flex items-center justify-between text-xs pt-2" style={{ color: "var(--text-faint)" }}>
        <div className="flex gap-3">
          <span>
            Racha + maxima: <strong style={{ color: "var(--text-muted)" }}>{metrics.longest_win_streak}</strong>
          </span>
          <span>
            Racha − maxima: <strong style={{ color: "var(--text-muted)" }}>{metrics.longest_loss_streak}</strong>
          </span>
          <span>
            Calmar: <strong style={{ color: "var(--text-muted)" }}>{metrics.calmar.toFixed(2)}</strong>
          </span>
        </div>
        <span>{durationSeconds != null ? `Calculado en ${durationSeconds.toFixed(2)}s` : ""}</span>
      </div>
    </div>
  );
}

function MetricBox({
  label,
  value,
  hint,
  tone = "neutral",
  large = false,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "green" | "red" | "neutral";
  large?: boolean;
}) {
  const color =
    tone === "green" ? "var(--green)" : tone === "red" ? "var(--red)" : "var(--text)";
  return (
    <div className="card p-3.5">
      <div className="text-[11px] uppercase tracking-wider mb-1.5" style={{ color: "var(--text-faint)" }}>
        {label}
      </div>
      <div className={`tabular-nums font-semibold ${large ? "text-xl" : "text-base"}`} style={{ color }}>
        {value}
      </div>
      {hint && (
        <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
          {hint}
        </div>
      )}
    </div>
  );
}
