"use client";

import Link from "next/link";
import { ArrowUpRight, Zap, Target, Clock, MoonStar } from "lucide-react";
import type { Strategy } from "@/lib/types";

const MARKET_ICON: Record<string, React.ReactNode> = {
  polymarket: <Target size={14} strokeWidth={1.75} />,
  crypto_perp: <Zap size={14} strokeWidth={1.75} />,
  options: <MoonStar size={14} strokeWidth={1.75} />,
};

const MARKET_LABEL: Record<string, string> = {
  polymarket: "Polymarket",
  crypto_perp: "Crypto Perp",
  options: "Options",
};

export function StrategyCard({
  strategy,
  backtestDisabled = false,
}: {
  strategy: Strategy;
  backtestDisabled?: boolean;
}) {
  const href = `/strategies/${encodeURIComponent(strategy.id)}`;
  const threshold = strategy.config.threshold;
  const dataset = strategy.config.dataset;

  return (
    <Link
      href={href}
      className="card p-5 transition-all hover:shadow-md group block relative"
      style={backtestDisabled ? { opacity: 0.72 } : undefined}
    >
      {backtestDisabled && (
        <span
          className="absolute top-3 right-3 text-[10px] uppercase tracking-wide px-2 py-0.5 rounded"
          style={{ background: "var(--bg-hover)", color: "var(--text-faint)" }}
        >
          Solo local
        </span>
      )}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="tag flex items-center gap-1.5">
            {MARKET_ICON[strategy.market_type] || null}
            {MARKET_LABEL[strategy.market_type] || strategy.market_type}
          </span>
          {strategy.tags.slice(0, 2).map((t) => (
            <span key={t} className="tag">
              {t}
            </span>
          ))}
        </div>
        <ArrowUpRight
          size={18}
          strokeWidth={1.75}
          className="opacity-30 group-hover:opacity-100 transition-opacity"
          style={{ color: "var(--text-muted)" }}
        />
      </div>

      <h3 className="font-semibold text-base mb-1.5" style={{ color: "var(--text)" }}>
        {strategy.name}
      </h3>
      <p className="text-sm mb-4 line-clamp-2" style={{ color: "var(--text-muted)" }}>
        {strategy.description}
      </p>

      <div className="flex items-center gap-4 pt-3 border-t" style={{ borderColor: "var(--border)" }}>
        {threshold !== undefined && (
          <Metric label="Edge min" value={`${(threshold * 100).toFixed(0)}pp`} />
        )}
        <Metric label="Stake" value={`$${strategy.stake}`} />
        <Metric label="Capital" value={`$${strategy.initial_bankroll}`} />
        {dataset && <Metric label="Data" value={dataset === "v4_real" ? "CLOB real" : "1y hist"} />}
      </div>
    </Link>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wider" style={{ color: "var(--text-faint)" }}>
        {label}
      </span>
      <span className="text-sm font-medium tabular-nums" style={{ color: "var(--text)" }}>
        {value}
      </span>
    </div>
  );
}
