"use client";

import { useMemo, useState } from "react";
import type { Trade } from "@/lib/types";
import { formatCurrency, formatDateTime } from "@/lib/api";

type MarketType = "polymarket" | "forex";
type StatusFilter = "all" | "win" | "loss";
type DirFilter = "all" | "long" | "short" | "up" | "down";
type SortKey = "date_desc" | "date_asc" | "pnl_desc" | "pnl_asc";

function normalizeDirection(d: string): "long" | "short" | "up" | "down" | "other" {
  const x = d.toLowerCase();
  if (x === "long" || x === "buy") return "long";
  if (x === "short" || x === "sell") return "short";
  if (x === "up") return "up";
  if (x === "down") return "down";
  return "other";
}

function directionLabel(d: string, market: MarketType): { text: string; color: string } {
  const n = normalizeDirection(d);
  if (market === "forex") {
    if (n === "long") return { text: "▲ Compra", color: "var(--green)" };
    if (n === "short") return { text: "▼ Venta", color: "var(--red)" };
  }
  if (n === "up" || n === "long") return { text: "▲ UP", color: "var(--green)" };
  if (n === "down" || n === "short") return { text: "▼ DOWN", color: "var(--red)" };
  return { text: d, color: "var(--text-muted)" };
}

export function TradesTable({
  trades,
  marketType = "polymarket",
}: {
  trades: Trade[];
  marketType?: MarketType;
}) {
  const [limit, setLimit] = useState(25);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [dirFilter, setDirFilter] = useState<DirFilter>("all");
  const [sort, setSort] = useState<SortKey>("date_desc");
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    let rows = [...trades];
    if (statusFilter === "win") rows = rows.filter((t) => t.is_winner);
    if (statusFilter === "loss") rows = rows.filter((t) => !t.is_winner);
    if (dirFilter !== "all") {
      rows = rows.filter((t) => {
        const n = normalizeDirection(t.direction);
        if (dirFilter === "long") return n === "long";
        if (dirFilter === "short") return n === "short";
        if (dirFilter === "up") return n === "up" || n === "long";
        if (dirFilter === "down") return n === "down" || n === "short";
        return true;
      });
    }
    const q = query.trim().toLowerCase();
    if (q) {
      rows = rows.filter((t) => {
        const date = formatDateTime(t.timestamp).toLowerCase();
        return date.includes(q) || t.asset.toLowerCase().includes(q) || t.direction.toLowerCase().includes(q);
      });
    }
    rows.sort((a, b) => {
      if (sort === "date_asc") return a.timestamp.localeCompare(b.timestamp);
      if (sort === "date_desc") return b.timestamp.localeCompare(a.timestamp);
      if (sort === "pnl_desc") return b.pnl - a.pnl;
      if (sort === "pnl_asc") return a.pnl - b.pnl;
      return 0;
    });
    return rows;
  }, [trades, statusFilter, dirFilter, sort, query]);

  if (!trades || trades.length === 0) {
    return (
      <div className="text-sm py-8 text-center" style={{ color: "var(--text-faint)" }}>
        No hay operaciones en este periodo
      </div>
    );
  }

  const shown = filtered.slice(0, limit);
  const isForex = marketType === "forex";

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-end">
        <FilterSelect
          label="Resultado"
          value={statusFilter}
          onChange={(v) => setStatusFilter(v as StatusFilter)}
          options={[
            ["all", "Todas"],
            ["win", "Ganadoras"],
            ["loss", "Perdedoras"],
          ]}
        />
        <FilterSelect
          label="Dirección"
          value={dirFilter}
          onChange={(v) => setDirFilter(v as DirFilter)}
          options={
            isForex
              ? [
                  ["all", "Todas"],
                  ["long", "Compra"],
                  ["short", "Venta"],
                ]
              : [
                  ["all", "Todas"],
                  ["up", "UP"],
                  ["down", "DOWN"],
                ]
          }
        />
        <FilterSelect
          label="Orden"
          value={sort}
          onChange={(v) => setSort(v as SortKey)}
          options={[
            ["date_desc", "Más recientes"],
            ["date_asc", "Más antiguas"],
            ["pnl_desc", "Mayor ganancia"],
            ["pnl_asc", "Mayor pérdida"],
          ]}
        />
        <div className="flex-1 min-w-[140px]">
          <label className="text-[10px] uppercase tracking-wider block mb-1" style={{ color: "var(--text-faint)" }}>
            Buscar
          </label>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Fecha, par…"
            className="w-full text-sm py-1.5 px-2 rounded-md border"
            style={{ borderColor: "var(--border)", background: "var(--bg-card)", color: "var(--text)" }}
          />
        </div>
      </div>

      <p className="text-xs" style={{ color: "var(--text-faint)" }}>
        Mostrando {shown.length} de {filtered.length} operaciones
        {filtered.length !== trades.length && ` (${trades.length} en total)`}
      </p>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left" style={{ color: "var(--text-faint)" }}>
              <th className="font-medium pb-2.5 pr-4 text-xs uppercase tracking-wider">Fecha</th>
              {!isForex && (
                <th className="font-medium pb-2.5 pr-4 text-xs uppercase tracking-wider">Asset</th>
              )}
              <th className="font-medium pb-2.5 pr-4 text-xs uppercase tracking-wider">Dir</th>
              <th className="font-medium pb-2.5 pr-4 text-xs uppercase tracking-wider text-right">
                {isForex ? "Entrada" : "Fill"}
              </th>
              {isForex && (
                <th className="font-medium pb-2.5 pr-4 text-xs uppercase tracking-wider text-right">Salida</th>
              )}
              {!isForex && (
                <th className="font-medium pb-2.5 pr-4 text-xs uppercase tracking-wider text-right">Stake</th>
              )}
              <th className="font-medium pb-2.5 pr-4 text-xs uppercase tracking-wider text-right">PnL</th>
              <th className="font-medium pb-2.5 pr-4 text-xs uppercase tracking-wider text-right">
                {isForex ? "Saldo" : "Bankroll"}
              </th>
              <th className="font-medium pb-2.5 text-xs uppercase tracking-wider text-right">Estado</th>
            </tr>
          </thead>
          <tbody>
            {shown.length === 0 ? (
              <tr>
                <td colSpan={isForex ? 7 : 8} className="py-8 text-center text-sm" style={{ color: "var(--text-faint)" }}>
                  Ninguna operación coincide con los filtros
                </td>
              </tr>
            ) : (
              shown.map((t, i) => {
                const dir = directionLabel(t.direction, marketType);
                return (
                  <tr
                    key={`${t.timestamp}-${i}`}
                    className="border-t transition-colors"
                    style={{ borderColor: "var(--border)" }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = "var(--bg-hover)";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = "transparent";
                    }}
                  >
                    <td className="py-2.5 pr-4 tabular-nums whitespace-nowrap" style={{ color: "var(--text-muted)" }}>
                      {formatDateTime(t.timestamp)}
                    </td>
                    {!isForex && (
                      <td className="py-2.5 pr-4 uppercase font-medium text-xs">{t.asset}</td>
                    )}
                    <td className="py-2.5 pr-4">
                      <span className="inline-flex items-center font-medium text-xs" style={{ color: dir.color }}>
                        {dir.text}
                      </span>
                    </td>
                    <td className="py-2.5 pr-4 tabular-nums text-right" style={{ color: "var(--text-muted)" }}>
                      {t.entry_price.toFixed(isForex ? 5 : 3)}
                    </td>
                    {isForex && (
                      <td className="py-2.5 pr-4 tabular-nums text-right" style={{ color: "var(--text-muted)" }}>
                        {t.exit_price.toFixed(5)}
                      </td>
                    )}
                    {!isForex && (
                      <td className="py-2.5 pr-4 tabular-nums text-right" style={{ color: "var(--text-muted)" }}>
                        ${t.stake_usd.toFixed(2)}
                      </td>
                    )}
                    <td
                      className="py-2.5 pr-4 tabular-nums text-right font-medium"
                      style={{ color: t.pnl >= 0 ? "var(--green)" : "var(--red)" }}
                    >
                      {t.pnl >= 0 ? "+" : ""}
                      {formatCurrency(t.pnl)}
                    </td>
                    <td className="py-2.5 pr-4 tabular-nums text-right" style={{ color: "var(--text-muted)" }}>
                      {formatCurrency(t.bankroll_after)}
                    </td>
                    <td className="py-2.5 text-right">
                      {t.is_winner ? (
                        <span className="tag" style={{ background: "var(--green-light)", color: "var(--green)" }}>
                          WIN
                        </span>
                      ) : (
                        <span className="tag" style={{ background: "var(--red-light)", color: "var(--red)" }}>
                          LOSS
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      {filtered.length > limit && (
        <div className="text-center mt-2">
          <button type="button" className="btn-secondary text-sm" onClick={() => setLimit((n) => n + 50)}>
            Ver más ({filtered.length - limit} restantes)
          </button>
        </div>
      )}
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
}) {
  return (
    <div>
      <label className="text-[10px] uppercase tracking-wider block mb-1" style={{ color: "var(--text-faint)" }}>
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="text-sm py-1.5 px-2 rounded-md border min-w-[120px]"
        style={{ borderColor: "var(--border)", background: "var(--bg-card)", color: "var(--text)" }}
      >
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </div>
  );
}
