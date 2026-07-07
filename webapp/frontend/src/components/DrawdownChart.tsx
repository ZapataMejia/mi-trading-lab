"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DrawdownPoint } from "@/lib/types";

export function DrawdownChart({ data, height = 180 }: { data: DrawdownPoint[]; height?: number }) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center text-sm" style={{ color: "var(--text-faint)", height }}>
        Sin datos
      </div>
    );
  }
  const chartData = data.map((d) => ({
    ts: new Date(d.timestamp).getTime(),
    dd: d.drawdown_pct,
  }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="dd-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--red)" stopOpacity={0.05} />
            <stop offset="100%" stopColor="var(--red)" stopOpacity={0.22} />
          </linearGradient>
        </defs>
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
          tickFormatter={(v) => `${v}%`}
          width={50}
          domain={["dataMin", 0]}
        />
        <Tooltip
          cursor={{ stroke: "var(--border-strong)", strokeWidth: 1 }}
          contentStyle={{
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            fontSize: 12,
            color: "var(--text)",
          }}
          formatter={(value) => {
            const num = typeof value === "number" ? value : Number(value ?? 0);
            return [`${num.toFixed(2)}%`, "Drawdown"];
          }}
          labelFormatter={(label) => new Date(label).toLocaleString("es-CO")}
        />
        <Area type="monotone" dataKey="dd" stroke="var(--red)" strokeWidth={1.5} fill="url(#dd-fill)" isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
