"use client";

import { useState } from "react";
import type { StrategyConfig } from "@/lib/types";
import { Sliders, RotateCcw } from "lucide-react";

const ASSETS = ["btc", "eth", "sol", "xrp"];
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export function ConfigEditor({
  base,
  current,
  onChange,
  onReset,
}: {
  base: StrategyConfig;        // config original (read-only baseline)
  current: StrategyConfig;     // editable
  onChange: (c: StrategyConfig) => void;
  onReset: () => void;
}) {
  const [open, setOpen] = useState(false);
  const dirty = JSON.stringify(base) !== JSON.stringify(current);

  function set<K extends keyof StrategyConfig>(k: K, v: StrategyConfig[K]) {
    onChange({ ...current, [k]: v });
  }

  function toggleAsset(a: string) {
    const filter = current.asset_filter || [];
    const next = filter.includes(a) ? filter.filter((x) => x !== a) : [...filter, a];
    set("asset_filter", next);
  }
  function toggleWeekday(d: string, mode: "skip" | "only") {
    const key = mode === "skip" ? "skip_weekdays" : "only_weekdays";
    const cur = current[key] || [];
    const next = cur.includes(d) ? cur.filter((x) => x !== d) : [...cur, d];
    set(key, next);
  }
  function toggleHour(h: number) {
    const cur = current.skip_hours_utc || [];
    const next = cur.includes(h) ? cur.filter((x) => x !== h) : [...cur, h];
    set("skip_hours_utc", next);
  }

  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between p-3.5 text-sm"
        style={{ color: "var(--text)" }}
      >
        <span className="inline-flex items-center gap-2 font-medium">
          <Sliders size={14} strokeWidth={1.75} />
          Parametros (editables sin tocar el codigo)
          {dirty && (
            <span className="tag" style={{ background: "var(--amber-light)", color: "var(--amber)" }}>
              modificado
            </span>
          )}
        </span>
        <span style={{ color: "var(--text-faint)" }}>{open ? "−" : "+"}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-4 border-t" style={{ borderColor: "var(--border)" }}>
          <div className="grid md:grid-cols-2 gap-4 mt-3">
            {/* Threshold */}
            <Field label="Threshold (edge mínimo)" hint={`${((current.threshold ?? 0) * 100).toFixed(0)} percentage points`}>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min={0}
                  max={50}
                  step={1}
                  value={(current.threshold ?? 0) * 100}
                  onChange={(e) => set("threshold", Number(e.target.value) / 100)}
                  className="flex-1"
                />
                <input
                  type="number"
                  min={0}
                  max={100}
                  step={1}
                  value={Math.round((current.threshold ?? 0) * 100)}
                  onChange={(e) => set("threshold", Math.max(0, Math.min(100, Number(e.target.value))) / 100)}
                  className="w-16 text-right tabular-nums"
                />
                <span className="text-xs" style={{ color: "var(--text-faint)" }}>pp</span>
              </div>
            </Field>

            {/* Volume */}
            <Field label="Volumen mínimo" hint={`$${(current.min_volume_usd ?? 0).toLocaleString()}`}>
              <input
                type="number"
                min={0}
                step={500}
                value={current.min_volume_usd ?? 0}
                onChange={(e) => set("min_volume_usd", Number(e.target.value))}
                className="w-full"
              />
            </Field>

            {/* Max seconds to resolution */}
            <Field
              label="Ventana max antes de resolución"
              hint={current.max_seconds_to_resolution ? `Últimos ${Math.round((current.max_seconds_to_resolution || 0) / 60)} min` : "Sin límite (cualquier momento)"}
            >
              <select
                value={current.max_seconds_to_resolution ?? 0}
                onChange={(e) => set("max_seconds_to_resolution", Number(e.target.value))}
                className="w-full"
              >
                <option value={0}>Sin limite (V1/V2 style)</option>
                <option value={60}>Ultimos 1 min</option>
                <option value={180}>Ultimos 3 min</option>
                <option value={300}>Ultimos 5 min (V4 style)</option>
                <option value={600}>Ultimos 10 min</option>
              </select>
            </Field>

            {/* Stake */}
            <Field label="Stake por trade" hint={`$${current.stake ?? 10}`}>
              <input
                type="number"
                min={1}
                step={1}
                value={current.stake as number ?? 10}
                onChange={(e) => set("stake", Number(e.target.value))}
                className="w-full"
              />
            </Field>
          </div>

          {/* Assets */}
          <Field label="Assets" hint={current.asset_filter?.length ? `Solo: ${current.asset_filter.join(", ")}` : "Todos los assets"}>
            <div className="flex gap-1.5">
              {ASSETS.map((a) => {
                const active = current.asset_filter?.includes(a);
                return (
                  <button
                    key={a}
                    onClick={() => toggleAsset(a)}
                    className="text-xs px-2.5 py-1 rounded-md uppercase tracking-wider transition-colors"
                    style={{
                      background: active ? "var(--bg-active)" : "transparent",
                      color: active ? "var(--text)" : "var(--text-muted)",
                      border: `1px solid ${active ? "var(--border-strong)" : "var(--border)"}`,
                      fontWeight: active ? 500 : 400,
                    }}
                  >
                    {a}
                  </button>
                );
              })}
            </div>
          </Field>

          {/* Skip Weekdays */}
          <Field label="Saltar días de la semana" hint={current.skip_weekdays?.length ? `Skip: ${current.skip_weekdays.join(", ")}` : "Opera todos los días"}>
            <div className="flex gap-1 flex-wrap">
              {WEEKDAYS.map((d) => {
                const active = current.skip_weekdays?.includes(d);
                return (
                  <button
                    key={d}
                    onClick={() => toggleWeekday(d, "skip")}
                    className="text-xs px-2.5 py-1 rounded-md transition-colors"
                    style={{
                      background: active ? "var(--red-light)" : "transparent",
                      color: active ? "var(--red)" : "var(--text-muted)",
                      border: `1px solid ${active ? "var(--red)" : "var(--border)"}`,
                      fontWeight: active ? 500 : 400,
                    }}
                  >
                    {d.slice(0, 3)}
                  </button>
                );
              })}
            </div>
          </Field>

          {/* Skip hours */}
          <Field
            label="Saltar horas UTC"
            hint={current.skip_hours_utc?.length ? `Skip: ${current.skip_hours_utc.sort((a, b) => a - b).map((h) => `${h}:00`).join(", ")}` : "Opera 24h"}
          >
            <div className="grid grid-cols-12 gap-1">
              {Array.from({ length: 24 }, (_, h) => {
                const active = current.skip_hours_utc?.includes(h);
                return (
                  <button
                    key={h}
                    onClick={() => toggleHour(h)}
                    className="text-xs h-7 rounded-md transition-colors tabular-nums"
                    style={{
                      background: active ? "var(--red-light)" : "transparent",
                      color: active ? "var(--red)" : "var(--text-muted)",
                      border: `1px solid ${active ? "var(--red)" : "var(--border)"}`,
                      fontWeight: active ? 500 : 400,
                    }}
                  >
                    {h}
                  </button>
                );
              })}
            </div>
          </Field>

          <div className="flex justify-end gap-2 pt-2">
            <button onClick={onReset} disabled={!dirty} className="btn-secondary inline-flex items-center gap-1.5">
              <RotateCcw size={13} strokeWidth={1.75} />
              Reset
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1.5">
        <label className="text-xs font-medium uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
          {label}
        </label>
        {hint && <span className="text-xs" style={{ color: "var(--text-faint)" }}>{hint}</span>}
      </div>
      {children}
    </div>
  );
}
