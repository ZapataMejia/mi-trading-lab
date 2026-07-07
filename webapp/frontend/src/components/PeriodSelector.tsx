"use client";

import { useState } from "react";
import { Calendar } from "lucide-react";

export type PeriodPreset = "7d" | "30d" | "90d" | "6m" | "1y" | "all" | "custom";

const PRESET_LABELS: Record<PeriodPreset, string> = {
  "7d": "7 días",
  "30d": "1 mes",
  "90d": "3 meses",
  "6m": "6 meses",
  "1y": "1 año",
  "all": "Todo",
  "custom": "Personalizado",
};

export interface PeriodRange {
  preset: PeriodPreset;
  start?: string;   // ISO date
  end?: string;
}

export function presetToRange(preset: PeriodPreset): { start?: string; end?: string } {
  if (preset === "all") return {};
  const now = new Date();
  const end = now.toISOString();
  const start = new Date(now);
  if (preset === "7d") start.setDate(start.getDate() - 7);
  else if (preset === "30d") start.setDate(start.getDate() - 30);
  else if (preset === "90d") start.setDate(start.getDate() - 90);
  else if (preset === "6m") start.setMonth(start.getMonth() - 6);
  else if (preset === "1y") start.setFullYear(start.getFullYear() - 1);
  return { start: start.toISOString(), end };
}

export function PeriodSelector({
  value,
  onChange,
}: {
  value: PeriodRange;
  onChange: (r: PeriodRange) => void;
}) {
  const [showCustom, setShowCustom] = useState(value.preset === "custom");

  function pickPreset(p: PeriodPreset) {
    if (p === "custom") {
      setShowCustom(true);
      onChange({ preset: "custom", start: value.start, end: value.end });
    } else {
      setShowCustom(false);
      const r = presetToRange(p);
      onChange({ preset: p, ...r });
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1">
        <Calendar size={14} strokeWidth={1.75} style={{ color: "var(--text-faint)" }} className="mr-1" />
        {(Object.keys(PRESET_LABELS) as PeriodPreset[]).map((p) => (
          <button
            key={p}
            onClick={() => pickPreset(p)}
            className="text-xs px-2.5 py-1 rounded-md transition-colors"
            style={{
              background: value.preset === p ? "var(--bg-active)" : "transparent",
              color: value.preset === p ? "var(--text)" : "var(--text-muted)",
              fontWeight: value.preset === p ? 500 : 400,
            }}
          >
            {PRESET_LABELS[p]}
          </button>
        ))}
      </div>
      {showCustom && (
        <div className="flex items-center gap-2 text-sm">
          <input
            type="date"
            value={value.start?.slice(0, 10) || ""}
            onChange={(e) => onChange({ ...value, preset: "custom", start: e.target.value })}
          />
          <span style={{ color: "var(--text-faint)" }}>→</span>
          <input
            type="date"
            value={value.end?.slice(0, 10) || ""}
            onChange={(e) => onChange({ ...value, preset: "custom", end: e.target.value })}
          />
        </div>
      )}
    </div>
  );
}
