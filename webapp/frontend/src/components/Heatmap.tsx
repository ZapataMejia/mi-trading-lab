"use client";

import type { HourBreakdown, WeekdayBreakdown } from "@/lib/types";

function colorScale(value: number, max: number): string {
  if (max === 0) return "var(--bg-hover)";
  const intensity = Math.min(1, Math.abs(value) / max);
  if (value >= 0) {
    return `color-mix(in srgb, var(--green) ${intensity * 70}%, var(--bg-card))`;
  } else {
    return `color-mix(in srgb, var(--red) ${intensity * 70}%, var(--bg-card))`;
  }
}

export function HourHeatmap({ data }: { data: HourBreakdown[] }) {
  const max = Math.max(...data.map((x) => Math.abs(x.pnl_total)), 1);
  return (
    <div>
      <div className="grid grid-cols-12 gap-1">
        {data.map((h) => (
          <div
            key={h.hour}
            className="rounded-md text-center py-2 px-1 transition-transform hover:scale-110"
            style={{
              background: colorScale(h.pnl_total, max),
              border: "1px solid var(--border)",
            }}
            title={`${h.hour}:00 UTC · ${h.trades} trades · WR ${h.win_rate_pct}% · $${h.pnl_total}`}
          >
            <div className="text-[10px] tabular-nums" style={{ color: "var(--text-muted)" }}>
              {h.hour}h
            </div>
            <div className="text-[11px] font-medium tabular-nums" style={{ color: h.pnl_total >= 0 ? "var(--green)" : "var(--red)" }}>
              {h.pnl_total >= 0 ? "+" : ""}
              {Math.round(h.pnl_total)}
            </div>
          </div>
        ))}
      </div>
      <div className="text-[10px] mt-2" style={{ color: "var(--text-faint)" }}>
        Cada celda = profit total en esa hora UTC · color = intensidad
      </div>
    </div>
  );
}

const WEEKDAY_LABEL: Record<string, string> = {
  Monday: "Lun",
  Tuesday: "Mar",
  Wednesday: "Mié",
  Thursday: "Jue",
  Friday: "Vie",
  Saturday: "Sáb",
  Sunday: "Dom",
};

export function WeekdayHeatmap({ data }: { data: WeekdayBreakdown[] }) {
  const max = Math.max(...data.map((x) => Math.abs(x.pnl_total)), 1);
  return (
    <div className="grid grid-cols-7 gap-1.5">
      {data.map((d) => (
        <div
          key={d.weekday}
          className="rounded-md text-center py-3 transition-transform hover:scale-105"
          style={{
            background: colorScale(d.pnl_total, max),
            border: "1px solid var(--border)",
          }}
        >
          <div className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
            {WEEKDAY_LABEL[d.weekday] || d.weekday.slice(0, 3)}
          </div>
          <div className="text-sm font-semibold tabular-nums mt-1" style={{ color: d.pnl_total >= 0 ? "var(--green)" : "var(--red)" }}>
            {d.pnl_total >= 0 ? "+" : ""}${Math.round(d.pnl_total)}
          </div>
          <div className="text-[10px] tabular-nums" style={{ color: "var(--text-faint)" }}>
            {d.trades} trades · {d.win_rate_pct}%
          </div>
        </div>
      ))}
    </div>
  );
}
