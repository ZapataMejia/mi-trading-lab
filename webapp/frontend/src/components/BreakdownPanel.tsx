"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type { BreakdownsResult } from "@/lib/types";
import { AssetBreakdown } from "./AssetBreakdown";
import { HourHeatmap, WeekdayHeatmap } from "./Heatmap";
import { PnlHistogram } from "./PnlHistogram";
import { DrawdownChart } from "./DrawdownChart";

export function BreakdownPanel({
  strategyId,
  periodStart,
  periodEnd,
  overrides,
  trigger,
}: {
  strategyId: string;
  periodStart?: string;
  periodEnd?: string;
  overrides?: Record<string, unknown>;
  trigger: number;
}) {
  const [data, setData] = useState<BreakdownsResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!strategyId || trigger === 0) return;
    setLoading(true);
    setError(null);
    api
      .getBreakdowns({ strategy_id: strategyId, period_start: periodStart, period_end: periodEnd, overrides })
      .then(setData)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strategyId, trigger]);

  if (loading) {
    return (
      <div className="card p-10 text-center">
        <Loader2 size={20} className="animate-spin mx-auto" style={{ color: "var(--accent)" }} />
        <p className="text-sm mt-2" style={{ color: "var(--text-muted)" }}>
          Calculando breakdowns...
        </p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="card p-4 text-sm" style={{ background: "var(--red-light)", color: "var(--red)" }}>
        {error}
      </div>
    );
  }
  if (!data) {
    return (
      <div className="card p-6 text-sm text-center" style={{ color: "var(--text-faint)" }}>
        Corré un backtest primero para ver los breakdowns
      </div>
    );
  }

  return (
    <div className="grid lg:grid-cols-2 gap-4">
      <Section title="Por asset">
        <AssetBreakdown data={data.by_asset} />
      </Section>

      <Section title="Distribucion de PnL por trade">
        <PnlHistogram data={data.pnl_histogram} />
      </Section>

      <Section title="Profit por dia de la semana" className="lg:col-span-2">
        <WeekdayHeatmap data={data.by_weekday} />
      </Section>

      <Section title="Profit por hora UTC" className="lg:col-span-2">
        <HourHeatmap data={data.by_hour} />
      </Section>

      <Section title="Drawdown" className="lg:col-span-2">
        <DrawdownChart data={data.drawdown_curve} />
      </Section>
    </div>
  );
}

function Section({ title, className, children }: { title: string; className?: string; children: React.ReactNode }) {
  return (
    <div className={`card p-5 ${className || ""}`}>
      <h3 className="text-sm font-semibold mb-4" style={{ color: "var(--text)" }}>
        {title}
      </h3>
      {children}
    </div>
  );
}
