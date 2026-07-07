"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { EquityPoint } from "@/lib/types";
import { formatCurrency } from "@/lib/api";

export function EquityChart({
  data,
  initialBankroll,
  height = 320,
}: {
  data: EquityPoint[];
  initialBankroll: number;
  height?: number;
}) {
  if (!data || data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-sm"
        style={{ color: "var(--text-faint)", height }}
      >
        Sin datos
      </div>
    );
  }
  const chartData = data
    .map((p) => ({
      ts: new Date(p.timestamp).getTime(),
      bankroll: p.bankroll,
      pnl: p.pnl_cumulative,
      trades: p.trades_to_date,
    }))
    .filter((p) => Number.isFinite(p.ts));

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center text-sm" style={{ color: "var(--text-faint)", height }}>
        Equity sin timestamps válidos
      </div>
    );
  }

  const finalBankroll = chartData[chartData.length - 1].bankroll;
  const positive = finalBankroll >= initialBankroll;
  const colorMain = positive ? "var(--green)" : "var(--red)";

  // Calculamos ticks manualmente — 6 puntos equispaciados — para garantizar
  // que el eje X siempre sea legible (recharts en algunos casos amontona ticks)
  const tsMin = chartData[0].ts;
  const tsMax = chartData[chartData.length - 1].ts;
  const N_TICKS = 6;
  const ticks =
    tsMin === tsMax
      ? [tsMin]
      : Array.from({ length: N_TICKS }, (_, i) => tsMin + ((tsMax - tsMin) * i) / (N_TICKS - 1));

  // Si el rango es menor a 3 dias, usar horas en el formato
  const rangeDays = (tsMax - tsMin) / (1000 * 60 * 60 * 24);
  const shortRange = rangeDays < 3;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="eq-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={colorMain as string} stopOpacity={0.18} />
            <stop offset="100%" stopColor={colorMain as string} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="ts"
          type="number"
          scale="time"
          domain={[tsMin, tsMax]}
          ticks={ticks}
          tickFormatter={(t) =>
            shortRange
              ? new Date(t).toLocaleString("es-CO", { day: "numeric", hour: "2-digit", minute: "2-digit" })
              : new Date(t).toLocaleDateString("es-CO", { month: "short", day: "numeric" })
          }
          stroke="var(--text-faint)"
          fontSize={11}
          tickLine={false}
          axisLine={false}
          minTickGap={40}
          interval="preserveStartEnd"
        />
        <YAxis
          stroke="var(--text-faint)"
          fontSize={11}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `$${v.toLocaleString()}`}
          width={70}
        />
        <Tooltip
          cursor={{ stroke: "var(--border-strong)", strokeWidth: 1 }}
          contentStyle={{
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            fontSize: 12,
            boxShadow: "var(--shadow)",
          }}
          formatter={(value, name) => {
            const num = typeof value === "number" ? value : Number(value ?? 0);
            if (name === "bankroll") return [formatCurrency(num), "Bankroll"];
            return [String(value ?? ""), String(name ?? "")];
          }}
          labelFormatter={(label) => new Date(label).toLocaleString("es-CO")}
        />
        <Area
          type="monotone"
          dataKey="bankroll"
          stroke={colorMain as string}
          strokeWidth={1.5}
          fill="url(#eq-fill)"
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
