"use client";

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PnlBucket } from "@/lib/types";

export function PnlHistogram({ data, height = 220 }: { data: PnlBucket[]; height?: number }) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center text-sm" style={{ color: "var(--text-faint)", height }}>
        Sin datos
      </div>
    );
  }
  const chartData = data.map((b) => ({
    label: `${b.bucket_lo.toFixed(0)}`,
    count: b.count,
    is_loss: b.bucket_hi < 0,
    is_win: b.bucket_lo >= 0,
    is_mixed: b.bucket_lo < 0 && b.bucket_hi >= 0,
    range: `$${b.bucket_lo.toFixed(2)} a $${b.bucket_hi.toFixed(2)}`,
  }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="label"
          stroke="var(--text-faint)"
          fontSize={10}
          tickLine={false}
          axisLine={false}
          interval={Math.floor(chartData.length / 12)}
        />
        <YAxis
          stroke="var(--text-faint)"
          fontSize={11}
          tickLine={false}
          axisLine={false}
          width={40}
        />
        <Tooltip
          cursor={{ fill: "var(--bg-hover)" }}
          contentStyle={{
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            fontSize: 12,
            color: "var(--text)",
          }}
          formatter={(value) => [`${value ?? 0} trades`, "Cantidad"]}
          labelFormatter={(_, payload) => (payload && payload[0]) ? payload[0].payload.range : ""}
        />
        <Bar dataKey="count" isAnimationActive={false}>
          {chartData.map((d, i) => (
            <Cell
              key={i}
              fill={d.is_win ? "var(--green)" : d.is_loss ? "var(--red)" : "var(--amber)"}
              fillOpacity={0.75}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
