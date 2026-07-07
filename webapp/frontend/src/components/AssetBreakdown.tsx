"use client";

import type { AssetBreakdown as AssetBreakdownType } from "@/lib/types";
import { formatCurrency } from "@/lib/api";

const ASSET_COLOR: Record<string, string> = {
  bitcoin: "#f7931a",
  ethereum: "#627eea",
  solana: "#14f195",
  xrp: "#00b3e6",
  btc: "#f7931a",
  eth: "#627eea",
  sol: "#14f195",
};

export function AssetBreakdown({ data }: { data: AssetBreakdownType[] }) {
  if (data.length === 0) {
    return (
      <div className="text-sm text-center py-6" style={{ color: "var(--text-faint)" }}>
        Sin trades para hacer breakdown
      </div>
    );
  }
  return (
    <div className="grid gap-2">
      {data.map((a) => (
        <div key={a.asset} className="flex items-center gap-4 py-2.5 px-3 rounded-md" style={{ background: "var(--bg-hover)" }}>
          <div
            className="w-2.5 h-2.5 rounded-full shrink-0"
            style={{ background: ASSET_COLOR[a.asset.toLowerCase()] || "var(--text-faint)" }}
          />
          <div className="font-semibold uppercase tracking-wider text-xs min-w-[80px]" style={{ color: "var(--text)" }}>
            {a.asset}
          </div>
          <div className="flex-1 grid grid-cols-3 gap-4 text-xs">
            <div>
              <span style={{ color: "var(--text-faint)" }}>Trades</span>
              <div className="font-medium tabular-nums" style={{ color: "var(--text)" }}>
                {a.trades}
              </div>
            </div>
            <div>
              <span style={{ color: "var(--text-faint)" }}>WR</span>
              <div
                className="font-medium tabular-nums"
                style={{ color: a.win_rate_pct >= 55 ? "var(--green)" : a.win_rate_pct < 45 ? "var(--red)" : "var(--text)" }}
              >
                {a.win_rate_pct.toFixed(1)}%
              </div>
            </div>
            <div>
              <span style={{ color: "var(--text-faint)" }}>Avg/trade</span>
              <div className="font-medium tabular-nums" style={{ color: a.pnl_avg >= 0 ? "var(--green)" : "var(--red)" }}>
                {a.pnl_avg >= 0 ? "+" : ""}${a.pnl_avg.toFixed(2)}
              </div>
            </div>
          </div>
          <div
            className="text-base font-semibold tabular-nums"
            style={{ color: a.pnl_total >= 0 ? "var(--green)" : "var(--red)" }}
          >
            {a.pnl_total >= 0 ? "+" : ""}
            {formatCurrency(a.pnl_total)}
          </div>
        </div>
      ))}
    </div>
  );
}
