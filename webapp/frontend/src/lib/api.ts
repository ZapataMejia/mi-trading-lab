// Cliente del backend FastAPI (localhost:8000 por default).

import type {
  BacktestResult,
  BreakdownsResult,
  LiveBotsResponse,
  Strategy,
  StrategiesResponse,
} from "./types";

import { getApiBase } from "./api-base";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${getApiBase()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return (await res.json()) as T;
}

export interface BacktestArgs {
  strategy_id: string;
  period_start?: string;
  period_end?: string;
  include_trades?: boolean;
  include_equity?: boolean;
  trades_limit?: number;
  equity_points?: number;
  overrides?: Record<string, unknown>;
}

export const api = {
  async listStrategies(marketType?: string): Promise<StrategiesResponse> {
    const q = marketType ? `?market_type=${encodeURIComponent(marketType)}` : "";
    return jsonFetch<StrategiesResponse>(`/api/strategies${q}`);
  },

  async getStrategy(id: string): Promise<Strategy> {
    return jsonFetch<Strategy>(`/api/strategies/${encodeURIComponent(id)}`);
  },

  async runBacktest(args: BacktestArgs): Promise<BacktestResult> {
    return jsonFetch<BacktestResult>(`/api/backtest/run`, {
      method: "POST",
      body: JSON.stringify({
        include_trades: true,
        include_equity: true,
        ...args,
      }),
    });
  },

  async getBreakdowns(args: BacktestArgs): Promise<BreakdownsResult> {
    return jsonFetch<BreakdownsResult>(`/api/backtest/breakdowns`, {
      method: "POST",
      body: JSON.stringify({ include_trades: false, include_equity: false, ...args }),
    });
  },

  async exportTradesUrl(args: BacktestArgs): Promise<string> {
    return `${getApiBase()}/api/backtest/export`;
  },

  async exportTrades(args: BacktestArgs): Promise<void> {
    const res = await fetch(`${getApiBase()}/api/backtest/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(args),
    });
    if (!res.ok) throw new Error(`Export failed: ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${args.strategy_id}_trades.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },

  async dataInfo(): Promise<Record<string, unknown>> {
    return jsonFetch<Record<string, unknown>>(`/api/backtest/data-info`);
  },

  async reloadStrategies(): Promise<{ loaded: number }> {
    return jsonFetch<{ loaded: number }>(`/api/strategies/reload`, { method: "POST" });
  },

  async health(): Promise<{ status: string }> {
    return jsonFetch<{ status: string }>(`/api/health`);
  },

  async capabilities(): Promise<{
    forex: boolean;
    polymarket: boolean;
    crypto: boolean;
    online_mode: boolean;
  }> {
    return jsonFetch(`/api/capabilities`);
  },

  async liveBots(): Promise<LiveBotsResponse> {
    return jsonFetch<LiveBotsResponse>(`/api/live/bots`);
  },

  async liveBotTrades(label: string, limit = 100): Promise<{ trades: Array<Record<string, unknown>>; total_closed: number }> {
    return jsonFetch(`/api/live/bots/${encodeURIComponent(label)}/trades?limit=${limit}`);
  },
};

export function formatCurrency(value: number, decimals = 2): string {
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function formatPct(value: number, decimals = 1): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(decimals)}%`;
}

export function formatDate(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("es-CO", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatDateTime(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("es-CO", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
