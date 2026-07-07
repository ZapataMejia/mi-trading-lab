"use client";

import { useMemo, useState } from "react";
import { formatCurrency } from "@/lib/api";

export interface ChartBar {
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
}

export interface TradeMarker {
  entry_time: string;
  exit_time: string;
  direction: string;
  entry_price: number;
  exit_price: number;
  sl?: number | null;
  tp?: number | null;
  pnl: number;
  won: boolean;
  reason?: string | null;
}

const PAD = { top: 16, right: 16, bottom: 36, left: 56 };

function nearestBarIndex(bars: ChartBar[], isoTime: string): number {
  const target = new Date(isoTime).getTime();
  if (!Number.isFinite(target)) return 0;
  let best = 0;
  let bestDiff = Infinity;
  for (let i = 0; i < bars.length; i++) {
    const diff = Math.abs(new Date(bars[i].t).getTime() - target);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = i;
    }
  }
  return best;
}

export function LiqSweepTradeChart({
  bars,
  markers,
  height = 400,
}: {
  bars: ChartBar[];
  markers: TradeMarker[];
  height?: number;
}) {
  const [selected, setSelected] = useState<number | null>(null);
  const width = 960;

  const layout = useMemo(() => {
    if (!bars.length) return null;

    let pMin = Infinity;
    let pMax = -Infinity;
    for (const b of bars) {
      pMin = Math.min(pMin, b.l);
      pMax = Math.max(pMax, b.h);
    }
    for (const m of markers) {
      pMin = Math.min(pMin, m.entry_price, m.sl ?? m.entry_price, m.tp ?? m.entry_price);
      pMax = Math.max(pMax, m.entry_price, m.sl ?? m.entry_price, m.tp ?? m.entry_price);
    }
    const pad = (pMax - pMin) * 0.08 || 0.0005;
    pMin -= pad;
    pMax += pad;

    const innerW = width - PAD.left - PAD.right;
    const innerH = height - PAD.top - PAD.bottom;
    const n = bars.length;

    const xAt = (i: number) => PAD.left + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);
    const yAt = (p: number) => PAD.top + ((pMax - p) / (pMax - pMin)) * innerH;
    const candleW = Math.max(2, Math.min(8, innerW / Math.max(n, 1) * 0.65));

    const markerPoints = markers.map((m, idx) => ({
      idx,
      m,
      barIndex: nearestBarIndex(bars, m.entry_time),
    }));

    return { pMin, pMax, xAt, yAt, candleW, innerW, innerH, markerPoints };
  }, [bars, markers, height]);

  if (!bars.length || !layout) {
    return (
      <div className="flex items-center justify-center text-sm" style={{ color: "var(--text-faint)", height }}>
        Sin datos de precio para graficar
      </div>
    );
  }

  const { xAt, yAt, candleW, markerPoints, pMin, pMax } = layout;
  const sel = selected != null ? markerPoints[selected] : null;

  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full min-w-[640px]" style={{ height }}>
        <rect x={0} y={0} width={width} height={height} fill="transparent" />

        {/* Grid horizontal */}
        {[0, 0.25, 0.5, 0.75, 1].map((f) => {
          const p = pMin + (pMax - pMin) * (1 - f);
          const y = yAt(p);
          return (
            <g key={f}>
              <line x1={PAD.left} x2={width - PAD.right} y1={y} y2={y} stroke="var(--border)" strokeDasharray="4 4" />
              <text x={PAD.left - 6} y={y + 4} textAnchor="end" fontSize={10} fill="var(--text-faint)">
                {p.toFixed(5)}
              </text>
            </g>
          );
        })}

        {/* SL / TP de operación seleccionada */}
        {sel?.m.sl != null && (
          <line
            x1={PAD.left}
            x2={width - PAD.right}
            y1={yAt(sel.m.sl)}
            y2={yAt(sel.m.sl)}
            stroke="var(--red)"
            strokeDasharray="6 4"
            opacity={0.7}
          />
        )}
        {sel?.m.tp != null && (
          <line
            x1={PAD.left}
            x2={width - PAD.right}
            y1={yAt(sel.m.tp)}
            y2={yAt(sel.m.tp)}
            stroke="var(--green)"
            strokeDasharray="6 4"
            opacity={0.7}
          />
        )}

        {/* Velas */}
        {bars.map((b, i) => {
          const x = xAt(i);
          const up = b.c >= b.o;
          const color = up ? "var(--green)" : "var(--red)";
          const bodyTop = yAt(Math.max(b.o, b.c));
          const bodyBot = yAt(Math.min(b.o, b.c));
          const bodyH = Math.max(1, bodyBot - bodyTop);
          return (
            <g key={`${b.t}-${i}`}>
              <line x1={x} x2={x} y1={yAt(b.h)} y2={yAt(b.l)} stroke={color} strokeWidth={1} />
              <rect
                x={x - candleW / 2}
                y={bodyTop}
                width={candleW}
                height={bodyH}
                fill={color}
                opacity={0.85}
              />
            </g>
          );
        })}

        {/* Marcadores compra / venta */}
        {markerPoints.map(({ idx, m, barIndex }) => {
          const x = xAt(barIndex);
          const y = yAt(m.entry_price);
          const isLong = m.direction === "long";
          const color = isLong ? "var(--green)" : "var(--red)";
          const active = selected === idx;
          const size = active ? 11 : 8;
          const points = isLong
            ? `${x},${y + size} ${x - size},${y - size * 0.6} ${x + size},${y - size * 0.6}`
            : `${x},${y - size} ${x - size},${y + size * 0.6} ${x + size},${y + size * 0.6}`;

          return (
            <g key={`${m.entry_time}-${idx}`}>
              <polygon
                points={points}
                fill={color}
                stroke="var(--bg-card)"
                strokeWidth={1.5}
                style={{ cursor: "pointer" }}
                onClick={() => setSelected(selected === idx ? null : idx)}
              />
              {active && (
                <text x={x} y={isLong ? y + 22 : y - 14} textAnchor="middle" fontSize={10} fill="var(--text)">
                  {isLong ? "Compra" : "Venta"} · {formatCurrency(m.pnl)}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      <div className="flex flex-wrap gap-4 text-xs mt-2" style={{ color: "var(--text-muted)" }}>
        <span className="inline-flex items-center gap-1">
          <span style={{ color: "var(--green)" }}>▲</span> Compra (long)
        </span>
        <span className="inline-flex items-center gap-1">
          <span style={{ color: "var(--red)" }}>▼</span> Venta (short)
        </span>
        <span>Toca un marcador para ver stop (rojo) y objetivo (verde)</span>
      </div>

      {sel && (
        <div className="mt-3 p-3 rounded-lg text-xs grid sm:grid-cols-2 gap-2" style={{ background: "var(--bg-hover)" }}>
          <div>
            <strong style={{ color: sel.m.direction === "long" ? "var(--green)" : "var(--red)" }}>
              {sel.m.direction === "long" ? "Compra" : "Venta"}
            </strong>
            {" · "}
            {new Date(sel.m.entry_time).toLocaleString("es-CO")}
          </div>
          <div>Entrada: {sel.m.entry_price.toFixed(5)} · Salida: {sel.m.exit_price.toFixed(5)}</div>
          <div>Stop: {sel.m.sl?.toFixed(5) ?? "—"} · Objetivo: {sel.m.tp?.toFixed(5) ?? "—"}</div>
          <div style={{ color: sel.m.won ? "var(--green)" : "var(--red)" }}>
            Resultado: {sel.m.pnl >= 0 ? "+" : ""}{formatCurrency(sel.m.pnl)} ({sel.m.won ? "ganancia" : "pérdida"})
          </div>
        </div>
      )}
    </div>
  );
}
