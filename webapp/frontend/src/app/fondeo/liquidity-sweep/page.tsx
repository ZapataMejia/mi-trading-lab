"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, Suspense } from "react";
import { ArrowLeft, CalendarDays, ChevronDown, ChevronUp, Clock, Download, HelpCircle, Loader2, PanelLeftClose, PanelLeftOpen, Play, Target, TrendingUp, Upload } from "lucide-react";
import { EquityChart } from "@/components/EquityChart";
import { LiqSweepTradeChart, type ChartBar, type TradeMarker } from "@/components/LiqSweepTradeChart";
import { MetricsGrid } from "@/components/MetricsGrid";
import { TradesTable } from "@/components/TradesTable";
import { useToast } from "@/components/Toast";
import { formatCurrency } from "@/lib/api";
import type { BacktestResult, EquityPoint, Trade } from "@/lib/types";
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { getApiBase } from "@/lib/api-base";
import { fetchErrorMessage, waitForBackend } from "@/lib/fetch-error";
import { useCapabilities } from "@/components/CapabilitiesProvider";
import {
  LIQ_SWEEP_TIMING,
  WS_META_USD,
  metaProgressPct,
  monthEvalBadge,
  monthEvalDetail,
} from "@/lib/liq-sweep-timing";

const SYMBOLS = [
  { id: "EURUSD", label: "EURUSD — Euro/Dólar" },
  { id: "GBPUSD", label: "GBPUSD — Libra/Dólar" },
  { id: "NAS100", label: "NAS100 — NASDAQ 100" },
] as const;

type SymbolId = (typeof SYMBOLS)[number]["id"];

interface LiqParams {
  timeframe: string;
  lookback_bars: number;
  equal_tolerance_pips: number;
  sess_start: number;
  sess_end: number;
  risk_pct: number;
  tp_ratio: number;
  sl_buffer_pips: number;
  max_trades_per_day: number;
  initial_balance: number;
  mm_risk_pct: number;
  broker_utc_offset_hours: number;
  allow_long: boolean;
  allow_short: boolean;
  period_start: string;
  period_end: string;
  use_regime_filter: boolean;
  adx_period: number;
  adx_min: number;
  adx_max: number;
  atr_period: number;
  min_atr_pips: number;
  max_atr_pips: number;
  require_equal_levels: boolean;
}

const MAX_CHART_DAYS = 45;
const AUTO_RUN_MAX_DAYS = 90;
/** Límite por simulación en la nube (PA free ~60 s). Local puede ser mayor. */
const MAX_SIM_DAYS_ONLINE = 90;
const MAX_SIM_DAYS_LOCAL = 400;
const FETCH_TIMEOUT_MS = 55000;
const YEAR_BREAKDOWN_TIMEOUT_MS = 300000;

/** Config base — Dual 2T maximiza meses que pasan eval (15/48 en 2022–2025) */
const SAFE_PRESET: Omit<LiqParams, "period_start" | "period_end"> = {
  timeframe: "M5",
  lookback_bars: 36,
  equal_tolerance_pips: 3,
  sess_start: 700,
  sess_end: 1400,
  risk_pct: 1.5,
  tp_ratio: 1.2,
  sl_buffer_pips: 3,
  max_trades_per_day: 2,
  initial_balance: 5000,
  mm_risk_pct: 1.5,
  broker_utc_offset_hours: 7,
  allow_long: true,
  allow_short: true,
  use_regime_filter: false,
  adx_period: 14,
  adx_min: 0,
  adx_max: 0,
  atr_period: 14,
  min_atr_pips: 0,
  max_atr_pips: 0,
  require_equal_levels: false,
};

const STRATEGY_PRESETS: {
  id: string;
  label: string;
  hint: string;
  badge?: string;
  patch: Partial<Omit<LiqParams, "period_start" | "period_end">>;
}[] = [
  {
    id: "dual",
    label: "Dual 2T — PASS WS",
    hint: "50% ventanas 30d · 15/48 meses · máx. probabilidad",
    badge: "Usar en eval",
    patch: { max_trades_per_day: 2, risk_pct: 1.5, mm_risk_pct: 1.5, tp_ratio: 1.2, lookback_bars: 36, sess_end: 1400, sl_buffer_pips: 3 },
  },
  {
    id: "aggressive",
    label: "Aggressive 2T",
    hint: "37.5% w30 · 15/48 meses · menos breaches que Dual",
    patch: {
      max_trades_per_day: 2, risk_pct: 1.25, mm_risk_pct: 1.25, tp_ratio: 1.5,
      lookback_bars: 36, sess_end: 1300, sl_buffer_pips: 2,
    },
  },
  {
    id: "monthly-safe",
    label: "Monthly Safe",
    hint: "8/48 pasan · 1 breach en 48 meses · TP 2.5R",
    badge: "Antibreach",
    patch: {
      lookback_bars: 60,
      sess_end: 1100,
      risk_pct: 1.0,
      mm_risk_pct: 1.0,
      tp_ratio: 2.5,
      sl_buffer_pips: 2,
      max_trades_per_day: 1,
    },
  },
  {
    id: "ultra-positive",
    label: "Ultra Positive",
    hint: "68.5% meses positivos · 0 breaches · riesgo 0.4%",
    badge: "Máx. verde",
    patch: {
      lookback_bars: 60,
      sess_start: 700,
      sess_end: 900,
      risk_pct: 0.4,
      mm_risk_pct: 0.4,
      tp_ratio: 1.0,
      sl_buffer_pips: 3,
      max_trades_per_day: 1,
    },
  },
  {
    id: "equal-51",
    label: "Equal 51.7% — récord EUR",
    hint: "51.7% meses pass eval · lb 24 · 7–14h · 2% · 1.2R · equal levels",
    badge: "Récord lab",
    patch: {
      lookback_bars: 24,
      equal_tolerance_pips: 3,
      sess_start: 700,
      sess_end: 1400,
      risk_pct: 2,
      mm_risk_pct: 2,
      tp_ratio: 1.2,
      sl_buffer_pips: 2,
      max_trades_per_day: 2,
      require_equal_levels: true,
    },
  },
  {
    id: "nas100",
    label: "NAS100 — índice",
    hint: "Sube CSV M5 de NASDAQ · tolerancia en puntos · sesión US",
    patch: {
      equal_tolerance_pips: 8,
      sl_buffer_pips: 5,
      sess_start: 1430,
      sess_end: 2100,
      max_trades_per_day: 3,
      require_equal_levels: false,
    },
  },
  {
    id: "safe",
    label: "SAFE",
    hint: "43.8% w30 · 14/48 meses · 1 trade/día",
    patch: { max_trades_per_day: 1, tp_ratio: 1.5, risk_pct: 1.5, mm_risk_pct: 1.5 },
  },
];

const DEFAULTS: LiqParams = {
  ...SAFE_PRESET,
  period_start: "2025-01-01",
  period_end: "2025-12-31",
};

interface WsEval {
  summary: string;
  static_dd_pct: number;
  max_daily_loss_pct: number;
  trading_days: number;
  days_to_meta: number | null;
  checks: Record<string, boolean>;
}

interface WsWindowSim {
  windows: {
    "14d": { pass_rate_pct: number; passed: number; attempts: number; median_days_to_meta: number | null };
    "30d": { pass_rate_pct: number; passed: number; attempts: number; median_days_to_meta: number | null };
  };
}

interface MonthlyRow {
  label: string;
  kind?: string;
  period_start: string;
  period_end: string;
  bars?: number;
  trades?: number;
  win_rate_pct?: number;
  total_pnl?: number;
  total_pnl_pct?: number;
  static_dd_pct?: number;
  max_daily_loss_pct?: number;
  trading_days?: number;
  days_to_meta?: number | null;
  pass_eval?: boolean;
  fail_reasons?: string[];
  error?: string;
}

interface MonthlyBreakdown {
  title: string;
  year: number;
  months: MonthlyRow[];
  ytd: MonthlyRow | null;
}

function hhmmLabel(v: number) {
  const h = Math.floor(v / 100);
  const m = v % 100;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function periodDays(start: string, end: string): number {
  const s = new Date(start + "T00:00:00");
  const e = new Date(end + "T00:00:00");
  return Math.max(1, Math.round((e.getTime() - s.getTime()) / 86400000) + 1);
}

function yearsInRange(dateFrom: string, dateTo: string): number[] {
  const y0 = parseInt(dateFrom.slice(0, 4), 10);
  const y1 = parseInt(dateTo.slice(0, 4), 10);
  if (Number.isNaN(y0) || Number.isNaN(y1)) return [];
  const out: number[] = [];
  for (let y = y1; y >= y0; y -= 1) out.push(y);
  return out;
}

function canShowPriceChart(p: LiqParams): boolean {
  return periodDays(p.period_start, p.period_end) <= MAX_CHART_DAYS;
}

const PRESET_FROM_URL: Record<string, { start: string; end: string }> = {
  "q1-2026": { start: "2026-01-01", end: "2026-03-31" },
  validate: { start: "2022-01-01", end: "2024-10-30" },
};

function formatDateEs(iso: string) {
  const d = new Date(`${iso}T12:00:00`);
  return d.toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" });
}

const PERIOD_EXAMPLES = [
  { label: "Ene–Mar 2026", start: "2026-01-01", end: "2026-03-31" },
  { label: "Enero 2026", start: "2026-01-01", end: "2026-01-31" },
  { label: "Oct–Dic 2025", start: "2025-10-01", end: "2025-12-31" },
] as const;

const MONTH_LABELS = [
  "",
  "Enero",
  "Febrero",
  "Marzo",
  "Abril",
  "Mayo",
  "Junio",
  "Julio",
  "Agosto",
  "Septiembre",
  "Octubre",
  "Noviembre",
  "Diciembre",
];

function monthEndIso(year: number, month: number): string {
  return new Date(Date.UTC(year, month, 0)).toISOString().slice(0, 10);
}

function clampIsoDate(iso: string, min?: string, max?: string): string {
  let out = iso;
  if (min && out < min) out = min;
  if (max && out > max) out = max;
  return out;
}

function formatRangeShort(start: string, end: string): string {
  const s = new Date(`${start}T12:00:00`);
  const e = new Date(`${end}T12:00:00`);
  const sm = s.toLocaleDateString("es-CO", { month: "short" }).replace(".", "");
  const em = e.toLocaleDateString("es-CO", { month: "short" }).replace(".", "");
  const sy = s.getFullYear();
  const ey = e.getFullYear();
  if (sy === ey) return `${sm}–${em} ${sy}`;
  return `${sm} ${sy} – ${em} ${ey}`;
}

function enumerateMonthsInRange(
  rangeStart: string,
  rangeEnd: string,
  bounds?: { date_from: string; date_to: string },
): { label: string; period_start: string; period_end: string }[] {
  if (rangeStart > rangeEnd) return [];
  const out: { label: string; period_start: string; period_end: string }[] = [];
  let y = parseInt(rangeStart.slice(0, 4), 10);
  let m = parseInt(rangeStart.slice(5, 7), 10);
  const endY = parseInt(rangeEnd.slice(0, 4), 10);
  const endM = parseInt(rangeEnd.slice(5, 7), 10);

  for (;;) {
    const rawStart = `${y}-${String(m).padStart(2, "0")}-01`;
    const rawEnd = monthEndIso(y, m);
    let ps = rawStart < rangeStart ? rangeStart : rawStart;
    let pe = rawEnd > rangeEnd ? rangeEnd : rawEnd;
    if (bounds) {
      ps = clampIsoDate(ps, bounds.date_from, bounds.date_to);
      pe = clampIsoDate(pe, bounds.date_from, bounds.date_to);
    }
    if (ps <= pe && ps <= rangeEnd && pe >= rangeStart) {
      out.push({ label: `${MONTH_LABELS[m]} ${y}`, period_start: ps, period_end: pe });
    }
    if (y === endY && m === endM) break;
    m += 1;
    if (m > 12) {
      m = 1;
      y += 1;
    }
  }
  return out;
}

function wsFailReasons(checks: Record<string, boolean> | undefined): string[] {
  if (!checks) return [];
  return Object.entries(checks)
    .filter(([k, ok]) => k.startsWith("pass_") && k !== "pass_all" && !ok)
    .map(([k]) => k.replace("pass_", ""));
}

function LiquiditySweepPageInner() {
  const searchParams = useSearchParams();
  const [params, setParams] = useState<LiqParams>(() => {
    const presetKey = searchParams.get("preset");
    const fromUrl = presetKey ? PRESET_FROM_URL[presetKey] : null;
    return fromUrl ? { ...DEFAULTS, period_start: fromUrl.start, period_end: fromUrl.end } : DEFAULTS;
  });
  const [symbol, setSymbol] = useState<SymbolId>("EURUSD");
  const [exporting, setExporting] = useState(false);
  const [running, setRunning] = useState(false);
  const [simError, setSimError] = useState<string | null>(null);
  const [simRunning, setSimRunning] = useState(false);
  const [result, setResult] = useState<(BacktestResult & { ws_eval?: WsEval; by_year?: YearRow[]; bars_used?: number }) | null>(null);
  const [windowSim, setWindowSim] = useState<WsWindowSim | null>(null);
  const [monthlyBreakdown, setMonthlyBreakdown] = useState<MonthlyBreakdown | null>(null);
  const [monthlyLoading, setMonthlyLoading] = useState(false);
  const [monthlyProgress, setMonthlyProgress] = useState<string | null>(null);
  const [yearToSimulate, setYearToSimulate] = useState(2026);
  const [dataInfo, setDataInfo] = useState("");
  const [dataRange, setDataRange] = useState<{ date_from: string; date_to: string; rows: number } | null>(null);
  const [showGuide, setShowGuide] = useState(true);
  const [activePresetId, setActivePresetId] = useState("dual");
  const [showParams, setShowParams] = useState(true);
  const [chartBars, setChartBars] = useState<ChartBar[]>([]);
  const [chartMarkers, setChartMarkers] = useState<TradeMarker[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [chartRequested, setChartRequested] = useState(false);
  const [showExamples, setShowExamples] = useState(false);
  const [breakdownView, setBreakdownView] = useState<"year" | "month" | null>(null);
  const [selectedMonthLabel, setSelectedMonthLabel] = useState<string | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const toast = useToast();
  const caps = useCapabilities();
  const isCloud =
    caps.online_mode ||
    getApiBase().includes("pythonanywhere.com") ||
    (typeof window !== "undefined" && window.location.hostname.includes("vercel.app"));
  const maxSimDays = caps.max_sim_days > 0 ? caps.max_sim_days : MAX_SIM_DAYS_LOCAL;
  const shortPeriodOnly = maxSimDays <= 90;
  const selectedDays = periodDays(params.period_start, params.period_end);
  const periodTooLong = selectedDays > maxSimDays;
  const rangeMonthSpecs = dataRange
    ? enumerateMonthsInRange(params.period_start, params.period_end, dataRange)
    : [];
  const rangeLabel = formatRangeShort(params.period_start, params.period_end);
  const availableYears = dataRange ? yearsInRange(dataRange.date_from, dataRange.date_to) : [];
  const showPriceChart = canShowPriceChart(params);
  const abortRef = useRef<AbortController | null>(null);
  const runInFlight = useRef(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const apiBase = getApiBase();
      const awake = await waitForBackend(apiBase, { attempts: 6, delayMs: 1500 });
      if (cancelled) return;
      if (!awake) {
        setDataRange(null);
        setDataInfo(
          isCloud
            ? "Backend no disponible — el servidor en la nube puede estar dormido."
            : "Backend no disponible — en terminal: cd trading && source .venv/bin/activate && uvicorn webapp.backend.main:app --port 8000",
        );
        return;
      }
      try {
        const r = await fetch(`${apiBase}/api/fondeo/data-range?symbol=${symbol}&timeframe=${params.timeframe}`);
        const j = await r.json();
        if (cancelled) return;
        if (j.available && j.date_from && j.date_to) {
          setDataRange({ date_from: j.date_from, date_to: j.date_to, rows: j.rows });
          setDataInfo(`${symbol} ${params.timeframe} · ${j.rows?.toLocaleString()} velas · ${j.date_from} → ${j.date_to}`);
        } else {
          setDataRange(null);
          setDataInfo(
            symbol === "NAS100"
              ? `Sin datos NAS100 — sube un CSV M5 con el botón «Subir CSV»`
              : `Sin datos ${symbol} — sube CSV M5 o usa otro par`,
          );
        }
      } catch {
        if (!cancelled) {
          setDataRange(null);
          setDataInfo("Backend no disponible");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [params.timeframe, symbol, isCloud]);

  useEffect(() => {
    if (!dataRange) return;
    const years = yearsInRange(dataRange.date_from, dataRange.date_to);
    if (years.length === 0) return;
    setYearToSimulate((y) => (years.includes(y) ? y : years[0]));
  }, [dataRange]);

  function datesOk(p: LiqParams): boolean {
    if (!dataRange) return true;
    if (p.period_start > p.period_end) return false;
    return p.period_start <= dataRange.date_to && p.period_end >= dataRange.date_from;
  }

  const datesOutOfRange = dataRange && !datesOk(params);
  const datesPartial = dataRange && datesOk(params) && (params.period_start < dataRange.date_from || params.period_end > dataRange.date_to);

  const runBacktest = useCallback(async (p: LiqParams, opts?: { fromMonth?: boolean }) => {
    if (runInFlight.current) return;
    if (dataRange && !datesOk(p)) {
      toast.push(
        `Fechas fuera de rango. Datos disponibles: ${dataRange.date_from} → ${dataRange.date_to}`,
        "error",
      );
      return;
    }
    const days = periodDays(p.period_start, p.period_end);
    if (days > maxSimDays) {
      const msg = `Periodo demasiado largo (${days} días). Máximo ${maxSimDays} días por simulación${
        shortPeriodOnly && isCloud ? " en la versión en línea" : ""
      }. Prueba un rango más corto o mes a mes.`;
      setSimError(msg);
      toast.push(msg, "error");
      return;
    }
    if (!opts?.fromMonth) {
      setBreakdownView(null);
      setSelectedMonthLabel(null);
      setMonthlyBreakdown(null);
    }
    runInFlight.current = true;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    setRunning(true);
    setSimError(null);
    try {
      const apiBase = getApiBase();
      const awake = await waitForBackend(apiBase, { attempts: 8, delayMs: 1500 });
      if (!awake) {
        throw new Error("Failed to fetch");
      }
      const body = {
        ...p,
        symbol,
        timeframe: p.timeframe,
        equity_sample_bars: 12,
        trades_limit: 150,
        equity_points: 120,
      };
      const res = await fetch(`${apiBase}/api/fondeo/liquidity-sweep/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      setResult(await res.json());
      setWindowSim(null);
    } catch (e) {
      const msg =
        fetchErrorMessage(e) ||
        "No se pudo completar la simulación. Prueba un periodo más corto (hasta 3 meses).";
      setSimError(msg);
      toast.push(msg, "error");
    } finally {
      clearTimeout(timeout);
      if (abortRef.current === controller) abortRef.current = null;
      runInFlight.current = false;
      setRunning(false);
    }
  }, [toast, dataRange, maxSimDays, shortPeriodOnly, isCloud, symbol]);

  const loadPriceChart = useCallback(async (p: LiqParams) => {
    if (!canShowPriceChart(p)) {
      setChartBars([]);
      setChartMarkers([]);
      return;
    }
    if (dataRange && !datesOk(p)) return;
    setChartLoading(true);
    try {
      const body = {
        ...p,
        symbol,
        timeframe: p.timeframe,
        equity_sample_bars: 12,
        max_bars: 1200,
        max_period_days: MAX_CHART_DAYS,
      };
      const res = await fetch(`${getApiBase()}/api/fondeo/liquidity-sweep/chart`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setChartBars(data.bars ?? []);
      setChartMarkers(data.markers ?? []);
    } catch {
      setChartBars([]);
      setChartMarkers([]);
    } finally {
      setChartLoading(false);
    }
  }, [dataRange, symbol]);

  const runWindowSim = useCallback(async () => {
    setSimRunning(true);
    try {
      const body = { ...params, symbol, timeframe: params.timeframe, equity_sample_bars: 12 };
      const res = await fetch(`${getApiBase()}/api/fondeo/liquidity-sweep/ws-eval-sim`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await res.text());
      setWindowSim(await res.json());
    } catch (e) {
      const msg = fetchErrorMessage(e);
      if (msg) toast.push(msg, "error");
    } finally {
      setSimRunning(false);
    }
  }, [params, toast, symbol]);

  const runMonthsBreakdown = useCallback(
    async (title: string, year: number, specs: { label: string; period_start: string; period_end: string }[]) => {
      if (!dataRange || specs.length === 0) return;
      setMonthlyLoading(true);
      setMonthlyBreakdown(null);
      setMonthlyProgress(null);
      setResult(null);
      setWindowSim(null);
      setSimError(null);
      setChartRequested(false);
      setBreakdownView(null);
      setSelectedMonthLabel(null);
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), YEAR_BREAKDOWN_TIMEOUT_MS);
      const apiBase = getApiBase();
      const rows: MonthlyRow[] = [];

      try {
        const awake = await waitForBackend(apiBase, { attempts: 8, delayMs: 1500 });
        if (!awake) throw new Error("Failed to fetch");

        for (let i = 0; i < specs.length; i += 1) {
          const { label, period_start, period_end } = specs[i];
          const monthDays = periodDays(period_start, period_end);
          if (monthDays <= 7 && period_end >= dataRange.date_to) {
            rows.push({ label, kind: "month", period_start, period_end, error: "no_data" });
            continue;
          }

          setMonthlyProgress(`${label} (${i + 1}/${specs.length})…`);

          const body = {
            ...params,
            symbol,
            timeframe: params.timeframe,
            period_start,
            period_end,
            equity_sample_bars: 12,
            trades_limit: 0,
            equity_points: 0,
          };

          try {
            const res = await fetch(`${apiBase}/api/fondeo/liquidity-sweep/run`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(body),
              signal: controller.signal,
            });
            if (!res.ok) {
              rows.push({ label, kind: "month", period_start, period_end, error: "no_data" });
              continue;
            }
            const data = (await res.json()) as BacktestResult & { ws_eval?: WsEval };
            const ev = data.ws_eval;
            rows.push({
              label,
              kind: "month",
              period_start,
              period_end,
              trades: data.metrics.n_trades,
              win_rate_pct: data.metrics.win_rate_pct,
              total_pnl: data.total_pnl,
              total_pnl_pct: data.total_pnl_pct,
              static_dd_pct: ev?.static_dd_pct,
              max_daily_loss_pct: ev?.max_daily_loss_pct,
              trading_days: ev?.trading_days,
              days_to_meta: ev?.days_to_meta ?? null,
              pass_eval: ev?.checks?.pass_all ?? false,
              fail_reasons: wsFailReasons(ev?.checks),
            });
          } catch (e) {
            if (controller.signal.aborted) throw e;
            rows.push({ label, kind: "month", period_start, period_end, error: "failed" });
          }
        }

        if (rows.length === 0) throw new Error("No hay datos para ese rango.");

        const okRows = rows.filter((r) => !r.error);
        const yearStart = specs[0].period_start;
        const yearEnd = specs[specs.length - 1].period_end;
        setYearToSimulate(year);
        setMonthlyBreakdown({ title, year, months: rows, ytd: null });
        setParams((prev) => ({ ...prev, period_start: yearStart, period_end: yearEnd }));
        setResult(null);
        setWindowSim(null);
        setSimError(null);
        setChartRequested(false);
        setBreakdownView("year");
        setSelectedMonthLabel(null);
        toast.push(
          `${title}: ${okRows.length} meses calculados${rows.length > okRows.length ? ` (${rows.length - okRows.length} sin datos)` : ""}`,
          "success",
        );
        setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 150);
      } catch (e) {
        toast.push(fetchErrorMessage(e) || "No se pudo calcular mes a mes. Inténtalo en unos segundos.", "error");
      } finally {
        clearTimeout(timeout);
        setMonthlyLoading(false);
        setMonthlyProgress(null);
      }
    },
    [dataRange, params, toast, symbol],
  );

  const runYearBreakdown = useCallback(
    async (year: number) => {
      if (!dataRange) return;
      const specs: { label: string; period_start: string; period_end: string }[] = [];
      for (let m = 1; m <= 12; m += 1) {
        const monthStartRaw = `${year}-${String(m).padStart(2, "0")}-01`;
        if (monthStartRaw > dataRange.date_to) break;
        if (monthEndIso(year, m) < dataRange.date_from) continue;
        const period_start = clampIsoDate(monthStartRaw, dataRange.date_from, dataRange.date_to);
        const period_end = clampIsoDate(monthEndIso(year, m), dataRange.date_from, dataRange.date_to);
        if (period_start > period_end) continue;
        specs.push({ label: `${MONTH_LABELS[m]} ${year}`, period_start, period_end });
      }
      await runMonthsBreakdown(String(year), year, specs);
    },
    [dataRange, runMonthsBreakdown],
  );

  const runRangeBreakdown = useCallback(
    async (rangeStart: string, rangeEnd: string) => {
      if (!dataRange) return;
      const specs = enumerateMonthsInRange(rangeStart, rangeEnd, dataRange);
      if (specs.length === 0) {
        toast.push("Revisa las fechas — no hay meses completos en ese rango.", "error");
        return;
      }
      const title = formatRangeShort(rangeStart, rangeEnd);
      const year = parseInt(rangeStart.slice(0, 4), 10);
      await runMonthsBreakdown(title, year, specs);
    },
    [dataRange, runMonthsBreakdown, toast],
  );

  const loadMonth = useCallback(
    (row: MonthlyRow) => {
      if (row.error || !row.period_start || !row.period_end) return;
      const next: LiqParams = { ...params, period_start: row.period_start, period_end: row.period_end };
      setParams(next);
      setSelectedMonthLabel(row.label);
      setBreakdownView("month");
      setResult(null);
      setWindowSim(null);
      setSimError(null);
      setChartRequested(false);
      void runBacktest(next, { fromMonth: true });
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
    },
    [params, runBacktest],
  );

  const backToYearOverview = useCallback(() => {
    if (!monthlyBreakdown) return;
    const okMonths = monthlyBreakdown.months.filter((m) => !m.error && m.period_start && m.period_end);
    if (okMonths.length > 0) {
      setParams((prev) => ({
        ...prev,
        period_start: okMonths[0].period_start!,
        period_end: okMonths[okMonths.length - 1].period_end!,
      }));
    }
    setBreakdownView("year");
    setSelectedMonthLabel(null);
    setResult(null);
    setWindowSim(null);
    setSimError(null);
    setChartRequested(false);
    setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
  }, [monthlyBreakdown]);

  // Gráfico de precio: bajo demanda (evita 2º backtest automático en la nube)
  useEffect(() => {
    setChartRequested(false);
    setChartBars([]);
    setChartMarkers([]);
  }, [params.period_start, params.period_end, params.timeframe]);

  useEffect(() => {
    if (!chartRequested || !result || !showPriceChart || datesOutOfRange) return;
    loadPriceChart(params);
  }, [chartRequested, result, params, showPriceChart, datesOutOfRange, loadPriceChart]);

  function set<K extends keyof LiqParams>(key: K, value: LiqParams[K]) {
    setParams((prev) => ({ ...prev, [key]: value }));
  }

  function onSymbolChange(next: SymbolId) {
    setSymbol(next);
    setParams((prev) => ({
      ...prev,
      equal_tolerance_pips:
        next === "NAS100"
          ? 8
          : prev.equal_tolerance_pips === 8
            ? 3
            : prev.equal_tolerance_pips,
    }));
    setResult(null);
    setWindowSim(null);
    setMonthlyBreakdown(null);
    setBreakdownView(null);
    setChartRequested(false);
  }

  async function onUploadCsv(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await fetch(
        `${getApiBase()}/api/fondeo/upload-csv?symbol=${symbol}&timeframe=${params.timeframe}`,
        { method: "POST", body: fd },
      );
      if (!res.ok) throw new Error(await res.text());
      const j = await res.json();
      toast.push(`CSV cargado: ${j.rows.toLocaleString()} barras (${symbol})`, "success");
      const dr = await fetch(`${getApiBase()}/api/fondeo/data-range?symbol=${symbol}&timeframe=${params.timeframe}`);
      const range = await dr.json();
      if (range.available) {
        setDataRange({ date_from: range.date_from, date_to: range.date_to, rows: range.rows });
        setDataInfo(`${symbol} ${params.timeframe} · ${range.rows?.toLocaleString()} velas · ${range.date_from} → ${range.date_to}`);
      }
    } catch (err) {
      toast.push(`Upload falló: ${String(err)}`, "error");
    }
    e.target.value = "";
  }

  async function exportTradesCsv() {
    if (datesOutOfRange || params.period_start > params.period_end || periodTooLong) {
      toast.push("Ajusta las fechas antes de exportar", "error");
      return;
    }
    setExporting(true);
    try {
      const body = {
        ...params,
        symbol,
        timeframe: params.timeframe,
        equity_sample_bars: 12,
        trades_limit: 0,
        equity_points: 0,
      };
      const res = await fetch(`${getApiBase()}/api/fondeo/liquidity-sweep/export-trades`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `trades_${symbol}_${params.period_start}_${params.period_end}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast.push("Trades exportados a CSV", "success");
    } catch (err) {
      toast.push(`Export falló: ${String(err)}`, "error");
    } finally {
      setExporting(false);
    }
  }

  const priceDecimals = symbol === "NAS100" ? 2 : 5;

  const trades = (result?.trades ?? []) as Trade[];
  const equity = (result?.equity_curve ?? []) as EquityPoint[];

  return (
    <div className="p-6 md:p-8 max-w-6xl mx-auto">
      <Link
        href="/fondeo"
        className="inline-flex items-center gap-1 text-xs mb-4"
        style={{ color: "var(--text-muted)" }}
      >
        <ArrowLeft size={14} />
        Volver al curso EMA Cross
      </Link>

      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight inline-flex items-center gap-2" style={{ color: "var(--text)" }}>
          <Target size={22} strokeWidth={1.75} />
          Liquidity Sweep — simulador
        </h1>
        <p className="text-sm mt-2 max-w-2xl" style={{ color: "var(--text-muted)" }}>
          Prueba la estrategia con datos históricos de <strong>{symbol}</strong> (EURUSD, GBPUSD o NAS100).
          Cuenta simulada de <strong>$5,000</strong> (como WS Funded).
        </p>
        <div className="flex flex-wrap items-center gap-3 mt-4">
          <div>
            <label className="text-[10px] uppercase tracking-wider block mb-1" style={{ color: "var(--text-faint)" }}>
              Mercado
            </label>
            <select
              value={symbol}
              onChange={(e) => onSymbolChange(e.target.value as SymbolId)}
              className="text-sm py-1.5 px-2 rounded-md border min-w-[200px]"
              style={{ borderColor: "var(--border)", background: "var(--bg-card)", color: "var(--text)" }}
            >
              {SYMBOLS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <label className="btn-secondary inline-flex items-center gap-2 cursor-pointer text-sm mt-4">
            <Upload size={14} />
            Subir CSV M5
            <input type="file" accept=".csv" className="hidden" onChange={onUploadCsv} />
          </label>
          <button
            type="button"
            className="btn-secondary inline-flex items-center gap-2 text-sm mt-4"
            disabled={exporting || running || !dataRange}
            onClick={() => void exportTradesCsv()}
          >
            {exporting ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
            Exportar trades CSV
          </button>
        </div>
        <p className="text-xs mt-2" style={{ color: "var(--text-faint)" }}>
          {dataInfo || "Cargando datos…"}
          {symbol === "NAS100" && " · Para NASDAQ sube tu CSV M5 (Dukascopy/SQX)."}
        </p>
      </header>

      <FundingTimelineBanner />

      <div
        className="card p-4 mb-4 border"
        style={{
          borderColor: "color-mix(in srgb, var(--accent) 35%, var(--border))",
          background: "color-mix(in srgb, var(--accent) 6%, var(--bg-card))",
        }}
      >
        <h2 className="text-sm font-semibold mb-2" style={{ color: "var(--text)" }}>
          Plan para pasar WS CLASSIC $5k
        </h2>
        <ol className="text-sm space-y-1.5 list-decimal list-inside" style={{ color: "var(--text-muted)" }}>
          <li><strong>No existe config que gane todos los meses</strong> en EURUSD — el techo histórico es ~68% meses positivos (preset Ultra Positive).</li>
          <li>Para <strong>pasar la eval</strong>: preset Dual 2T + 2 cuentas (~75% que una pase en 30 días).</li>
          <li>Para <strong>no romper la cuenta</strong>: preset Ultra Positive (0 breaches, pero casi no llega a +$400/mes).</li>
        </ol>
      </div>

      <div className="card p-4 mb-4">
        <div className="text-xs uppercase tracking-wider mb-2" style={{ color: "var(--text-faint)" }}>
          Presets estrategia · WS CLASSIC $5k
        </div>
        <div className="flex flex-wrap gap-2">
          {STRATEGY_PRESETS.map((preset) => {
            const active = activePresetId === preset.id;
            return (
              <button
                key={preset.id}
                type="button"
                onClick={() => {
                  setActivePresetId(preset.id);
                  setParams((p) => ({
                    ...p,
                    ...SAFE_PRESET,
                    ...preset.patch,
                    mm_risk_pct: preset.patch.mm_risk_pct ?? preset.patch.risk_pct ?? SAFE_PRESET.mm_risk_pct,
                  }));
                }}
                className="text-left rounded-lg px-3 py-2 border transition-colors"
                style={{
                  borderColor: active ? "var(--accent)" : "var(--border)",
                  background: active
                    ? "color-mix(in srgb, var(--accent) 12%, var(--bg-card))"
                    : "var(--bg-hover)",
                }}
              >
                <div className="text-sm font-semibold flex items-center gap-2" style={{ color: "var(--text)" }}>
                  {preset.label}
                  {preset.badge && (
                    <span
                      className="text-[10px] px-1.5 py-0.5 rounded font-medium"
                      style={{ background: "color-mix(in srgb, var(--green) 20%, transparent)", color: "var(--green)" }}
                    >
                      {preset.badge}
                    </span>
                  )}
                </div>
                <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                  {preset.hint}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="card p-4 mb-4 border" style={{ borderColor: "var(--border)" }}>
        <button
          type="button"
          className="w-full flex items-center justify-between gap-2 text-left"
          onClick={() => setShowGuide((v) => !v)}
        >
          <span className="inline-flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--text)" }}>
            <HelpCircle size={18} />
            ¿Qué hace esta estrategia?
          </span>
          {showGuide ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </button>
        {showGuide && (
          <div className="mt-4 space-y-4 text-sm" style={{ color: "var(--text-muted)" }}>
            <p>
              Es una estrategia de <strong style={{ color: "var(--text)" }}>reversión</strong> en forex (EURUSD, velas de 5 minutos).
              Busca momentos en que el precio <strong>barre stops</strong> de otros traders y luego <strong>vuelve</strong>.
            </p>
            <ol className="list-decimal pl-5 space-y-2">
              <li>Mira el máximo y mínimo de las últimas ~3 horas (36 velas).</li>
              <li>Si el precio <strong>sobrepasa</strong> ese nivel con la mecha pero <strong>cierra del otro lado</strong>, hay una señal.</li>
              <li>Entra en <strong>contra</strong> del barrido (si barrió arriba → vende; si barrió abajo → compra).</li>
              <li>Stop detrás del extremo del barrido; objetivo = 1,5× lo que arriesgas.</li>
            </ol>
            <div className="grid sm:grid-cols-2 gap-3 text-xs">
              <div className="rounded-lg p-3" style={{ background: "var(--bg-hover)" }}>
                <div className="font-semibold mb-1" style={{ color: "var(--text)" }}>Reglas WS CLASSIC $5k (oficial)</div>
                <ul className="space-y-1">
                  <li>· Fase 1: +$400 (+8%) · Fase 2: +$250 (+5%)</li>
                  <li>· DD diario 5% · DD estático 8% · mín. 4 días</li>
                  <li>· Riesgo máx. 2,5% por trade · SL en 2 min</li>
                  <li>· Sin consistency rule · EAs permitidos</li>
                  <li>· Trades/día: sin límite WS (lab: gestión de riesgo)</li>
                </ul>
                <div className="font-semibold mb-1 mt-2" style={{ color: "var(--text)" }}>Preset estrategia (lab)</div>
                <ul className="space-y-1">
                  <li>· Riesgo: 1,5% · hasta 2 trades/día</li>
                  <li>· Horario: 07:00 – 14:00 (hora broker)</li>
                </ul>
              </div>
              <div className="rounded-lg p-3" style={{ background: "var(--bg-hover)" }}>
                <div className="font-semibold mb-1" style={{ color: "var(--text)" }}>Cómo leer los resultados</div>
                <ul className="space-y-1">
                  <li>· <strong style={{ color: "var(--green)" }}>Pasa eval</strong> = cumple todas las reglas WS ese mes</li>
                  <li>· <strong style={{ color: "var(--green)" }}>Rentable</strong> = ganó dinero aunque no llegue a +$400 en 30 días</li>
                  <li>· En la vida real suele tomar <strong>{LIQ_SWEEP_TIMING.estimatedMonthsLabel}</strong> (reintentos de eval)</li>
                  <li>· Para ver muchos meses: <strong>Simular mes a mes</strong> (bloque 2)</li>
                </ul>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="card p-5 mb-4">
        <h2 className="text-base font-semibold mb-1" style={{ color: "var(--text)" }}>
          1. Elige las fechas que quieres probar
        </h2>
        <p className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>
          Tú decides el rango. Cambia <strong>desde</strong> y <strong>hasta</strong>, luego pulsa <strong>Simular</strong>.
        </p>

        {dataRange ? (
          <div
            className="rounded-lg p-4 mb-4 text-sm border"
            style={{
              background: "color-mix(in srgb, var(--accent) 8%, var(--bg-card))",
              borderColor: "color-mix(in srgb, var(--accent) 25%, var(--border))",
            }}
          >
            <div className="font-semibold mb-1" style={{ color: "var(--text)" }}>
              Datos disponibles en el servidor
            </div>
            <p style={{ color: "var(--text-muted)" }}>
              Histórico entre{" "}
              <strong style={{ color: "var(--text)" }}>{formatDateEs(dataRange.date_from)}</strong> y{" "}
              <strong style={{ color: "var(--text)" }}>{formatDateEs(dataRange.date_to)}</strong>
              {" "}({dataRange.rows.toLocaleString()} velas M5 de {symbol}).
            </p>
            <p className="mt-2 text-xs" style={{ color: "var(--text-faint)" }}>
              Hasta <strong>{maxSimDays} días</strong> por clic en “Simular este periodo”
              {shortPeriodOnly && isCloud ? " (límite del servidor en la nube)" : ""}.
              {shortPeriodOnly
                ? " ¿Semestre o año entero? Usa mes a mes abajo — mismo backtest, un mes por vez."
                : " Puedes probar semestres o años enteros en un solo clic."}
            </p>
          </div>
        ) : (
          <p className="text-xs mb-4 px-3 py-2 rounded" style={{ color: "var(--text-muted)", background: "var(--bg-hover)" }}>
            {dataInfo || "Cargando rango de datos…"}
          </p>
        )}

        <div className="grid sm:grid-cols-2 gap-4 max-w-xl mb-3">
          <DateField
            label="Desde (inicio)"
            value={params.period_start}
            min={dataRange?.date_from}
            max={dataRange?.date_to}
            onChange={(v) => set("period_start", v)}
          />
          <DateField
            label="Hasta (fin)"
            value={params.period_end}
            min={dataRange?.date_from}
            max={dataRange?.date_to}
            onChange={(v) => set("period_end", v)}
          />
        </div>

        <p className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>
          Periodo seleccionado: <strong>{periodDays(params.period_start, params.period_end)} días</strong>
          {params.period_start > params.period_end && (
            <span style={{ color: "var(--red)" }}> · La fecha de inicio no puede ser posterior a la de fin</span>
          )}
        </p>

        {periodTooLong && !datesOutOfRange && params.period_start <= params.period_end && rangeMonthSpecs.length > 0 && shortPeriodOnly && (
          <div
            className="mb-4 p-4 rounded-lg border-2"
            style={{ borderColor: "var(--accent)", background: "color-mix(in srgb, var(--accent) 8%, var(--bg-card))" }}
          >
            <p className="text-sm font-medium" style={{ color: "var(--text)" }}>
              Sí puedes probar {rangeLabel} — solo no cabe en un solo clic
            </p>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              El servidor gratuito procesa máx. {maxSimDays} días por tanda. Pulsa aquí y te calcula{" "}
              <strong>{rangeMonthSpecs.length} meses</strong> automático (uno tras otro). Es la forma de hacer un semestre o un año.
            </p>
            <button
              type="button"
              className="btn-primary text-sm inline-flex items-center gap-2 mt-3"
              disabled={monthlyLoading}
              onClick={() => runRangeBreakdown(params.period_start, params.period_end)}
            >
              {monthlyLoading ? <Loader2 size={14} className="animate-spin" /> : <CalendarDays size={14} />}
              {monthlyLoading
                ? monthlyProgress ?? "Calculando mes a mes…"
                : `Simular ${rangeLabel} mes a mes (${rangeMonthSpecs.length} meses)`}
            </button>
          </div>
        )}

        {periodTooLong && shortPeriodOnly && (
          <p className="text-xs mb-3 px-3 py-2 rounded" style={{ color: "var(--text-muted)", background: "var(--bg-hover)" }}>
            “Simular este periodo” admite hasta {maxSimDays} días. Para {selectedDays} días usa el botón azul de arriba o el bloque 2.
          </p>
        )}
        {datesOutOfRange && dataRange && (
          <p className="text-xs mb-3 px-3 py-2 rounded" style={{ color: "var(--red)", background: "color-mix(in srgb, var(--red) 12%, transparent)" }}>
            Esas fechas quedan fuera del rango disponible. Ajusta entre {formatDateEs(dataRange.date_from)} y {formatDateEs(dataRange.date_to)}.
          </p>
        )}
        {datesPartial && dataRange && (
          <p className="text-xs mb-3 px-3 py-2 rounded" style={{ color: "var(--yellow, #b8860b)", background: "color-mix(in srgb, #b8860b 12%, transparent)" }}>
            Parte del rango que elegiste no tiene datos; la simulación usará solo lo que exista entre {formatDateEs(dataRange.date_from)} y {formatDateEs(dataRange.date_to)}.
          </p>
        )}

        <div className="flex items-center gap-3 mt-2 flex-wrap">
          <button
            onClick={() => runBacktest(params)}
            disabled={running || !!datesOutOfRange || params.period_start > params.period_end || periodTooLong}
            className="btn-primary inline-flex items-center gap-2"
          >
            {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            {running ? "Calculando…" : "Simular este periodo"}
          </button>
          <span className="text-xs" style={{ color: "var(--text-faint)" }}>
            {periodTooLong
              ? `Máx. ${maxSimDays} días por simulación`
              : selectedDays > AUTO_RUN_MAX_DAYS
                ? "Periodo largo: puede tardar ~30–60 s"
                : "Periodos cortos (≤ 3 meses) suelen tardar unos segundos"}
          </span>
        </div>

        <div className="mt-4 pt-4 border-t" style={{ borderColor: "var(--border)" }}>
          <button
            type="button"
            className="text-xs inline-flex items-center gap-1"
            style={{ color: "var(--text-muted)" }}
            onClick={() => setShowExamples((v) => !v)}
          >
            {showExamples ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            Ejemplos de fechas (opcional)
          </button>
          {showExamples && (
            <div className="flex flex-wrap gap-2 mt-3">
              {PERIOD_EXAMPLES.map((ex) => (
                <button
                  key={ex.label}
                  type="button"
                  onClick={() => setParams((prev) => ({ ...prev, period_start: ex.start, period_end: ex.end }))}
                  className="px-3 py-1.5 rounded-lg text-xs border"
                  style={{ borderColor: "var(--border)", background: "var(--bg-hover)", color: "var(--text-muted)" }}
                >
                  {ex.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {dataRange && availableYears.length > 0 && (
        <div className="card p-5 mb-4">
          <div className="flex items-start justify-between gap-3 mb-4 flex-wrap">
            <div>
              <h2 className="text-base font-semibold inline-flex items-center gap-2" style={{ color: "var(--text)" }}>
                <CalendarDays size={18} strokeWidth={1.75} />
                2. Semestre o año → mes a mes
              </h2>
              <p className="text-sm mt-1 max-w-xl" style={{ color: "var(--text-muted)" }}>
                Para ver muchos meses seguidos (6, 12…). Cada mes = cuenta de $5,000. Toca un mes para el detalle con trades.
              </p>
            </div>
            <button
              type="button"
              className="btn-primary text-sm inline-flex items-center gap-2 shrink-0"
              disabled={monthlyLoading}
              onClick={() => runYearBreakdown(yearToSimulate)}
            >
              {monthlyLoading ? <Loader2 size={14} className="animate-spin" /> : <CalendarDays size={14} />}
              {monthlyLoading ? "Calculando 12 meses…" : `Simular ${yearToSimulate} mes a mes`}
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-2 mb-4">
            <span className="text-xs uppercase tracking-wider" style={{ color: "var(--text-faint)" }}>
              Año:
            </span>
            {availableYears.slice(0, 12).map((y) => (
              <button
                key={y}
                type="button"
                onClick={() => {
                  setYearToSimulate(y);
                  if (monthlyBreakdown?.year !== y) {
                    setMonthlyBreakdown(null);
                    setBreakdownView(null);
                    setSelectedMonthLabel(null);
                  }
                }}
                className="px-3 py-1.5 rounded-lg text-xs border"
                style={{
                  borderColor: yearToSimulate === y ? "var(--accent)" : "var(--border)",
                  background: yearToSimulate === y ? "color-mix(in srgb, var(--accent) 12%, var(--bg-card))" : "var(--bg-hover)",
                  color: yearToSimulate === y ? "var(--accent)" : "var(--text-muted)",
                  fontWeight: yearToSimulate === y ? 600 : 400,
                }}
              >
                {y}
              </button>
            ))}
            {availableYears.length > 12 && (
              <select
                value={yearToSimulate}
                onChange={(e) => {
                  const y = Number(e.target.value);
                  setYearToSimulate(y);
                  if (monthlyBreakdown?.year !== y) {
                    setMonthlyBreakdown(null);
                    setBreakdownView(null);
                    setSelectedMonthLabel(null);
                  }
                }}
                className="text-xs py-1.5 px-2 rounded-lg border"
                style={{ borderColor: "var(--border)", background: "var(--bg-card)", color: "var(--text)" }}
              >
                {availableYears.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            )}
          </div>

          {monthlyLoading && (
            <p className="text-xs mb-3 inline-flex items-center gap-2" style={{ color: "var(--text-muted)" }}>
              <Loader2 size={12} className="animate-spin" />
              {monthlyProgress ?? `Simulando ${yearToSimulate} mes a mes…`}
              {" "}(~5–10 s por mes en la nube)
            </p>
          )}

          {!monthlyBreakdown && !monthlyLoading && (
            <p className="text-xs" style={{ color: "var(--text-faint)" }}>
              Elige un año abajo o usa el botón azul arriba con tus fechas. Los resultados aparecen en «Periodo simulado» abajo.
            </p>
          )}

          {monthlyBreakdown && breakdownView === "year" && (
            <p className="text-xs px-3 py-2 rounded" style={{ color: "var(--green)", background: "color-mix(in srgb, var(--green) 10%, var(--bg-card))" }}>
              Desglose listo — revisa «Periodo simulado» más abajo. Toca un mes para ver trades, gráfico y eval WS.
            </p>
          )}

          {monthlyBreakdown && breakdownView === "month" && (
            <>
              <YearBreakdownSummary months={monthlyBreakdown.months} title={monthlyBreakdown.title} />
              <p className="text-xs mb-3 mt-4" style={{ color: "var(--text-muted)" }}>
                Toca otro mes o usa «Volver» en los resultados.
              </p>
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {monthlyBreakdown.months.map((row) => (
                  <MonthCard
                    key={row.label}
                    row={row}
                    onSelect={() => loadMonth(row)}
                    selected={selectedMonthLabel === row.label}
                  />
                ))}
                {monthlyBreakdown.ytd && (
                  <MonthCard
                    row={monthlyBreakdown.ytd}
                    onSelect={() => loadMonth(monthlyBreakdown.ytd!)}
                    highlight
                    selected={selectedMonthLabel === monthlyBreakdown.ytd.label}
                  />
                )}
              </div>
            </>
          )}
        </div>
      )}

      <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
        <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-faint)" }}>
          Parámetros avanzados (opcional)
        </p>
        <button
          type="button"
          className="btn-secondary text-xs inline-flex items-center gap-1.5"
          onClick={() => setShowParams((v) => !v)}
        >
          {showParams ? <PanelLeftClose size={14} /> : <PanelLeftOpen size={14} />}
          {showParams ? "Ocultar panel" : "Mostrar panel"}
        </button>
      </div>

      <div className={`grid gap-4 ${showParams ? "lg:grid-cols-[320px_1fr]" : "grid-cols-1"}`}>
        {showParams && (
        <aside className="card p-4 space-y-4 order-2 lg:order-1">
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>
            Ajustes finos de la estrategia. Para probar fechas, usa el bloque de arriba.
          </p>

          <Section title="Liquidez">
            <Slider label="Lookback (barras M5)" value={params.lookback_bars} min={6} max={96} step={6} onChange={(v) => set("lookback_bars", v)} />
            <Slider
              label="Tolerancia equal H/L"
              value={params.equal_tolerance_pips}
              min={0}
              max={symbol === "NAS100" ? 20 : 10}
              step={0.5}
              onChange={(v) => set("equal_tolerance_pips", v)}
              suffix={symbol === "NAS100" ? " pts" : " pips"}
            />
            <label className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: "var(--text-muted)" }}>
              <input
                type="checkbox"
                checked={params.require_equal_levels}
                onChange={(e) => set("require_equal_levels", e.target.checked)}
              />
              Requerir equal highs/lows
            </label>
            <Slider label="Buffer SL" value={params.sl_buffer_pips} min={0} max={10} step={0.5} onChange={(v) => set("sl_buffer_pips", v)} suffix=" pips" />
          </Section>

          <Section title="Riesgo / TP">
            <Slider label="Risk %" value={params.risk_pct} min={0.5} max={2.5} step={0.1} onChange={(v) => set("risk_pct", v)} suffix="%" />
            <Slider label="TP ratio (R)" value={params.tp_ratio} min={1} max={4} step={0.1} onChange={(v) => set("tp_ratio", v)} />
            <Slider label="MM riesgo %" value={params.mm_risk_pct} min={0.5} max={2.5} step={0.1} onChange={(v) => set("mm_risk_pct", v)} suffix="%" />
          </Section>

          <Section title="Sesión (hora broker)">
            <Slider label="Offset UTC" value={params.broker_utc_offset_hours} min={-12} max={12} step={1} onChange={(v) => set("broker_utc_offset_hours", v)} suffix=" h" />
            <Slider label="Inicio" value={params.sess_start} min={0} max={2359} step={5} onChange={(v) => set("sess_start", v)} format={hhmmLabel} />
            <Slider label="Fin" value={params.sess_end} min={0} max={2359} step={5} onChange={(v) => set("sess_end", v)} format={hhmmLabel} />
            <Slider label="Max trades/día" value={params.max_trades_per_day} min={1} max={10} step={1} onChange={(v) => set("max_trades_per_day", v)} />
          </Section>

          <Section title="Cuenta">
            <Slider label="Capital inicial" value={params.initial_balance} min={5000} max={50000} step={500} onChange={(v) => set("initial_balance", v)} prefix="$" />
          </Section>

          <Section title="Dirección">
            <Toggle label="Long (sweep low)" checked={params.allow_long} onChange={(v) => set("allow_long", v)} />
            <Toggle label="Short (sweep high)" checked={params.allow_short} onChange={(v) => set("allow_short", v)} />
          </Section>
        </aside>
        )}

        <main ref={resultsRef} className="space-y-4 min-w-0 order-1 lg:order-2">
          {monthlyLoading && (
            <div className="card p-12 text-center text-sm" style={{ color: "var(--text-muted)" }}>
              <Loader2 size={24} className="animate-spin mx-auto mb-3" />
              {monthlyProgress ?? `Calculando ${yearToSimulate} mes a mes…`}
              <p className="text-xs mt-2" style={{ color: "var(--text-faint)" }}>
                ~5–10 s por mes · los resultados aparecerán aquí
              </p>
            </div>
          )}

          {!monthlyLoading && breakdownView === "year" && monthlyBreakdown && (
            <>
              <div className="card p-5">
                <div className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--text-faint)" }}>
                  Periodo simulado · {monthlyBreakdown.title} (mes a mes)
                </div>
                <p className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>
                  {formatDateEs(params.period_start)} → {formatDateEs(params.period_end)} ·{" "}
                  {monthlyBreakdown.months.filter((m) => !m.error).length} meses · cada uno con cuenta nueva de $5,000
                </p>
                <YearBreakdownSummary months={monthlyBreakdown.months} title={monthlyBreakdown.title} />
              </div>
              <div className="card p-5">
                <h3 className="text-sm font-semibold mb-1" style={{ color: "var(--text)" }}>
                  Evolución del año
                </h3>
                <p className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>
                  Barras = resultado de cada mes (cuenta nueva de $5,000). Línea = suma acumulada del año.
                </p>
                <YearMonthlyChart months={monthlyBreakdown.months} />
              </div>
              <div className="card p-5">
                <h3 className="text-sm font-semibold mb-1" style={{ color: "var(--text)" }}>
                  Toca un mes para ver el detalle
                </h3>
                <p className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>
                  Gráfico, operaciones y evaluación WS Funded del mes seleccionado.
                </p>
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                  {monthlyBreakdown.months.map((row) => (
                    <MonthCard key={row.label} row={row} onSelect={() => loadMonth(row)} />
                  ))}
                  {monthlyBreakdown.ytd && (
                    <MonthCard row={monthlyBreakdown.ytd} onSelect={() => loadMonth(monthlyBreakdown.ytd!)} highlight />
                  )}
                </div>
              </div>
            </>
          )}

          {!monthlyLoading && result && breakdownView !== "year" ? (
            <>
              {breakdownView === "month" && monthlyBreakdown && (
                <button
                  type="button"
                  onClick={backToYearOverview}
                  className="btn-secondary text-sm inline-flex items-center gap-1.5"
                >
                  <ArrowLeft size={14} />
                  Volver a {monthlyBreakdown.title} mes a mes
                </button>
              )}
              <div className="card p-5">
                <div className="flex items-baseline justify-between mb-4 flex-wrap gap-2">
                  <div>
                    <div className="text-xs uppercase tracking-wider" style={{ color: "var(--text-faint)" }}>
                      Periodo simulado
                      {breakdownView === "month" && selectedMonthLabel
                        ? ` · ${selectedMonthLabel}`
                        : ` · ${formatDateEs(params.period_start)} → ${formatDateEs(params.period_end)}`}
                    </div>
                    <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                      {breakdownView === "month" && selectedMonthLabel && (
                        <span>{formatDateEs(params.period_start)} → {formatDateEs(params.period_end)} · </span>
                      )}
                      {periodDays(params.period_start, params.period_end)} días · {trades.length} operaciones en este rango
                    </p>
                    <div className="text-2xl font-semibold tabular-nums" style={{ color: result.total_pnl >= 0 ? "var(--green)" : "var(--red)" }}>
                      Ganancia total: {result.total_pnl >= 0 ? "+" : ""}{formatCurrency(result.total_pnl)}
                      <span className="text-sm font-normal ml-2" style={{ color: "var(--text-muted)" }}>
                        ({result.total_pnl_pct >= 0 ? "+" : ""}{result.total_pnl_pct}%)
                      </span>
                    </div>
                    <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                      Saldo final simulado: {formatCurrency(result.final_bankroll)} · {trades.length} operaciones
                    </p>
                  </div>
                </div>
                <MetricsGrid
                  metrics={result.metrics}
                  initialBankroll={result.initial_bankroll}
                  finalBankroll={result.final_bankroll}
                  totalPnl={result.total_pnl}
                  totalPnlPct={result.total_pnl_pct}
                  durationSeconds={result.duration_seconds}
                />
              </div>

              {result.ws_eval && (
                <div className="card p-4">
                  <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
                    <h3 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
                      ¿Pasaría la evaluación WS Funded?
                    </h3>
                    <button onClick={runWindowSim} disabled={simRunning} className="btn-secondary text-xs px-3 py-1.5">
                      {simRunning ? "Calculando…" : "Probabilidad histórica"}
                    </button>
                  </div>
                  <p className="text-base font-medium mb-3" style={{ color: result.ws_eval.checks.pass_all ? "var(--green)" : "var(--red)" }}>
                    {result.ws_eval.checks.pass_all
                      ? "Sí — en este periodo la cuenta simulada cumple las reglas."
                      : "No — en este periodo la cuenta simulada no cumple todas las reglas."}
                  </p>
                  <p className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>{result.ws_eval.summary}</p>
                  <div className="grid sm:grid-cols-2 gap-2 text-xs">
                    {[
                      ["Meta +8% ($400)", result.ws_eval.checks.pass_meta],
                      ["Pérdida total ≤ 8%", result.ws_eval.checks.pass_static_dd],
                      ["Peor día ≤ 5%", result.ws_eval.checks.pass_daily_dd],
                      ["Al menos 4 días operando", result.ws_eval.checks.pass_min_days],
                      ["Más ganancias que pérdidas (PF)", result.ws_eval.checks.pass_pf],
                      ["Riesgo por trade OK", result.ws_eval.checks.pass_risk],
                    ].map(([label, ok]) => (
                      <div key={label as string} className="flex justify-between px-2 py-1 rounded" style={{ background: "var(--bg-hover)" }}>
                        <span style={{ color: "var(--text-muted)" }}>{label}</span>
                        <span style={{ color: ok ? "var(--green)" : "var(--red)" }}>{ok ? "✓" : "✗"}</span>
                      </div>
                    ))}
                  </div>
                  <p className="text-xs mt-2" style={{ color: "var(--text-faint)" }}>
                    DD {result.ws_eval.static_dd_pct}% · DD día max {result.ws_eval.max_daily_loss_pct}% ·
                    {result.ws_eval.trading_days} días con trades
                    {result.ws_eval.days_to_meta != null && ` · meta en ${result.ws_eval.days_to_meta}d`}
                  </p>
                  {windowSim && (
                    <div className="mt-3 pt-3 border-t text-xs grid sm:grid-cols-2 gap-2" style={{ borderColor: "var(--border)" }}>
                      <div>
                        <strong>14 días:</strong> {windowSim.windows["14d"].passed}/{windowSim.windows["14d"].attempts} ({windowSim.windows["14d"].pass_rate_pct}%)
                      </div>
                      <div>
                        <strong>30 días:</strong> {windowSim.windows["30d"].passed}/{windowSim.windows["30d"].attempts} ({windowSim.windows["30d"].pass_rate_pct}%)
                        {windowSim.windows["30d"].median_days_to_meta != null && ` · med ${windowSim.windows["30d"].median_days_to_meta}d`}
                      </div>
                    </div>
                  )}
                </div>
              )}

              <div className="card p-4 text-xs" style={{ color: "var(--text-muted)" }}>
                <strong style={{ color: "var(--text)" }}>Lógica:</strong> en cada barra M5, si el precio barre el swing high/low de las últimas N barras y cierra de vuelta dentro → entrada en contra. SL detrás del extremo del sweep. TP = ratio × riesgo.
              </div>

              <div className="card p-5">
                <h3 className="text-sm font-semibold mb-1" style={{ color: "var(--text)" }}>
                  Gráfico de precio — dónde compra y vende
                </h3>
                <p className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>
                  {showPriceChart
                    ? `Velas ${symbol} M5. Triángulo verde = compra · rojo = venta. Toca una operación para ver stop y objetivo.`
                    : `Disponible en periodos de hasta ${MAX_CHART_DAYS} días. Prueba “Ene–Mar 2026” o un mes del desglose.`}
                </p>
                {showPriceChart ? (
                  !chartRequested ? (
                    <button
                      type="button"
                      className="btn-secondary text-sm"
                      onClick={() => setChartRequested(true)}
                    >
                      Cargar gráfico de operaciones
                    </button>
                  ) : chartLoading ? (
                    <div className="flex items-center justify-center gap-2 text-sm py-16" style={{ color: "var(--text-faint)" }}>
                      <Loader2 size={16} className="animate-spin" />
                      Cargando gráfico…
                    </div>
                  ) : chartMarkers.length > 0 ? (
                    <LiqSweepTradeChart bars={chartBars} markers={chartMarkers} />
                  ) : (
                    <div className="text-sm py-12 text-center" style={{ color: "var(--text-faint)" }}>
                      No hubo operaciones en este periodo.
                    </div>
                  )
                ) : (
                  <div className="text-sm py-8 text-center rounded-lg" style={{ background: "var(--bg-hover)", color: "var(--text-muted)" }}>
                    Elige un periodo corto (por ejemplo un mes de 2026) para ver las entradas en el gráfico.
                  </div>
                )}
              </div>

              <div className="card p-5">
                <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--text)" }}>Evolución de la cuenta</h3>
                <EquityChart data={equity} initialBankroll={result.initial_bankroll} />
              </div>

              <div className="card p-5">
                <h3 className="text-sm font-semibold mb-1" style={{ color: "var(--text)" }}>
                  Operaciones
                </h3>
                <p className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>
                  Lista de trades del periodo simulado{trades.length >= 150 ? " (máx. 150 mostradas; usa «Exportar trades CSV» para todas)" : ""}.
                </p>
                <TradesTable trades={trades.slice().reverse()} marketType="forex" priceDecimals={priceDecimals} />
              </div>
            </>
          ) : !monthlyLoading && breakdownView !== "year" ? (
            <div className="card p-12 text-center text-sm" style={{ color: "var(--text-faint)" }}>
              {running ? (
                "Calculando resultados… (puede tardar hasta 1 minuto)"
              ) : simError ? (
                <span style={{ color: "var(--red)" }}>{simError}</span>
              ) : (
                "Elige las fechas arriba y pulsa «Simular este periodo», o usa «Semestre o año → mes a mes» para ver un año completo aquí."
              )}
            </div>
          ) : null}
        </main>
      </div>
    </div>
  );
}

interface YearRow {
  year: string;
  trades: number;
  wins: number;
  win_rate_pct: number;
  pnl: number;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-xs uppercase tracking-wider mb-2" style={{ color: "var(--text-faint)" }}>{title}</h3>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  onChange,
  suffix = "",
  prefix = "",
  format,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  suffix?: string;
  prefix?: string;
  format?: (v: number) => string;
}) {
  const display = format ? format(value) : `${prefix}${value}${suffix}`;
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span style={{ color: "var(--text-muted)" }}>{label}</span>
        <span className="tabular-nums font-medium" style={{ color: "var(--text)" }}>{display}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="w-full" />
    </div>
  );
}

function DateField({ label, value, onChange, min, max }: { label: string; value: string; onChange: (v: string) => void; min?: string; max?: string }) {
  return (
    <div>
      <label className="text-sm font-medium block mb-2" style={{ color: "var(--text)" }}>{label}</label>
      <input
        type="date"
        value={value}
        min={min}
        max={max}
        onChange={(e) => onChange(e.target.value)}
        className="w-full text-base py-2.5 px-3 rounded-lg border"
        style={{ borderColor: "var(--border)", background: "var(--bg-card)", color: "var(--text)" }}
      />
    </div>
  );
}

function FundingTimelineBanner() {
  const t = LIQ_SWEEP_TIMING;
  return (
    <div
      className="card p-5 mb-4 border-2"
      style={{
        borderColor: "color-mix(in srgb, var(--green) 35%, var(--border))",
        background: "linear-gradient(135deg, color-mix(in srgb, var(--green) 10%, var(--bg-card)), var(--bg-card))",
      }}
    >
      <div className="flex items-start gap-3">
        <div
          className="rounded-full p-2 shrink-0"
          style={{ background: "color-mix(in srgb, var(--green) 18%, transparent)" }}
        >
          <Clock size={20} style={{ color: "var(--green)" }} />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold" style={{ color: "var(--text)" }}>
            ¿Cuánto tarda en pasar la cuenta de fondeo?
          </h2>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
            Con esta estrategia, en datos reales de EURUSD, la mayoría de personas planifica{" "}
            <strong style={{ color: "var(--text)" }}>{t.estimatedMonthsLabel}</strong> desde que empiezan hasta pasar la eval WS.
            No es un mes mágico: son intentos de ~30 días, y si uno falla se reintenta.
          </p>
          <div className="grid sm:grid-cols-3 gap-3 mt-4 text-sm">
            <div className="rounded-lg p-3" style={{ background: "var(--bg-hover)" }}>
              <div className="text-[10px] uppercase tracking-wider mb-1" style={{ color: "var(--text-faint)" }}>
                Cuando pasa
              </div>
              <div className="font-semibold tabular-nums" style={{ color: "var(--green)" }}>
                ~{t.medianDaysWhenPasses} días
              </div>
              <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                Dentro del intento que sí pasa
              </div>
            </div>
            <div className="rounded-lg p-3" style={{ background: "var(--bg-hover)" }}>
              <div className="text-[10px] uppercase tracking-wider mb-1" style={{ color: "var(--text-faint)" }}>
                Meses que pasan eval
              </div>
              <div className="font-semibold tabular-nums" style={{ color: "var(--text)" }}>
                {t.monthlyPassCount}/{t.monthlyTotal} ({Math.round(t.passRateMonthlyPct)}%)
              </div>
              <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                Cuenta nueva cada mes calendario (2022–2025)
              </div>
            </div>
            <div className="rounded-lg p-3" style={{ background: "var(--bg-hover)" }}>
              <div className="text-[10px] uppercase tracking-wider mb-1" style={{ color: "var(--text-faint)" }}>
                Ventanas 30 días
              </div>
              <div className="font-semibold tabular-nums" style={{ color: "var(--text)" }}>
                ~{Math.round(t.passRate30dPct)}%
              </div>
              <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                Arranque cualquier día (no = mes calendario)
              </div>
            </div>
            <div className="rounded-lg p-3" style={{ background: "var(--bg-hover)" }}>
              <div className="text-[10px] uppercase tracking-wider mb-1" style={{ color: "var(--text-faint)" }}>
                Con 2 cuentas
              </div>
              <div className="font-semibold tabular-nums" style={{ color: "var(--text)" }}>
                ~{Math.round(t.probTwoAccountsPct)}%
              </div>
              <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                Al menos una pasa en el 1er intento
              </div>
            </div>
          </div>
          <p className="text-[10px] mt-3 inline-flex items-center gap-1" style={{ color: "var(--text-faint)" }}>
            <TrendingUp size={12} />
            {t.dataNote}. Pasar el 100% de meses no es posible en datos reales — el objetivo es maximizar cuántos meses pasan sin romper la cuenta.
          </p>
        </div>
      </div>
    </div>
  );
}

function YearMonthlyChart({ months }: { months: MonthlyRow[] }) {
  let cumulative = 0;
  const chartData = months
    .filter((m) => !m.error && m.total_pnl != null)
    .map((m) => {
      const pnl = m.total_pnl ?? 0;
      cumulative += pnl;
      const monthWord = m.label.split(" ")[0] ?? m.label;
      return {
        label: monthWord.slice(0, 3),
        fullLabel: m.label,
        pnl,
        cumulative,
        pass: m.pass_eval ?? false,
      };
    });

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center text-sm" style={{ color: "var(--text-faint)", height: 280 }}>
        Sin datos para graficar
      </div>
    );
  }

  const totalPnl = chartData[chartData.length - 1]?.cumulative ?? 0;
  const lineColor = totalPnl >= 0 ? "var(--green)" : "var(--red)";

  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="label"
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
          tickFormatter={(v) => `$${v.toLocaleString()}`}
          width={70}
        />
        <Tooltip
          cursor={{ fill: "color-mix(in srgb, var(--accent) 8%, transparent)" }}
          contentStyle={{
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            fontSize: 12,
            boxShadow: "var(--shadow)",
          }}
          formatter={(value, name) => {
            const num = typeof value === "number" ? value : Number(value ?? 0);
            if (name === "pnl") return [formatCurrency(num), "Mes"];
            if (name === "cumulative") return [formatCurrency(num), "Acumulado"];
            return [String(value ?? ""), String(name ?? "")];
          }}
          labelFormatter={(_, payload) => {
            const row = payload?.[0]?.payload as { fullLabel?: string } | undefined;
            return row?.fullLabel ?? "";
          }}
        />
        <Bar dataKey="pnl" radius={[4, 4, 0, 0]} isAnimationActive={false}>
          {chartData.map((entry) => (
            <Cell
              key={entry.fullLabel}
              fill={entry.pnl >= 0 ? "color-mix(in srgb, var(--green) 75%, var(--bg-card))" : "color-mix(in srgb, var(--red) 75%, var(--bg-card))"}
            />
          ))}
        </Bar>
        <Line
          type="monotone"
          dataKey="cumulative"
          stroke={lineColor}
          strokeWidth={2}
          dot={{ r: 3, fill: lineColor }}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function YearBreakdownSummary({ months, title }: { months: MonthlyRow[]; title: string }) {
  const valid = months.filter((m) => !m.error && m.trades != null);
  if (valid.length === 0) return null;

  const passed = valid.filter((m) => m.pass_eval).length;
  const profitable = valid.filter((m) => (m.total_pnl ?? 0) > 0).length;
  const metaHit = valid.filter((m) => (m.total_pnl ?? 0) >= WS_META_USD).length;
  const totalPnl = valid.reduce((s, m) => s + (m.total_pnl ?? 0), 0);
  const totalTrades = valid.reduce((s, m) => s + (m.trades ?? 0), 0);
  const best = valid.reduce((a, b) => ((b.total_pnl ?? 0) > (a.total_pnl ?? 0) ? b : a));
  const worst = valid.reduce((a, b) => ((b.total_pnl ?? 0) < (a.total_pnl ?? 0) ? b : a));

  return (
    <div
      className="rounded-lg p-4 grid sm:grid-cols-2 lg:grid-cols-4 gap-4 text-sm border"
      style={{ background: "var(--bg-hover)", borderColor: "var(--border)" }}
    >
      <div>
        <div className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--text-faint)" }}>
          Tiempo para pasar eval
        </div>
        <div className="font-semibold" style={{ color: "var(--green)" }}>
          {LIQ_SWEEP_TIMING.estimatedMonthsLabel}
        </div>
        <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
          Histórico · ~{LIQ_SWEEP_TIMING.medianDaysWhenPasses}d cuando pasa
        </div>
      </div>
      <div>
        <div className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--text-faint)" }}>
          Este rango ({title})
        </div>
        <div style={{ color: "var(--text)" }}>
          <strong style={{ color: profitable > 0 ? "var(--green)" : "var(--text)" }}>{profitable}</strong> meses rentables
          {passed > 0 && (
            <>
              {" "}· <strong style={{ color: "var(--green)" }}>{passed}</strong> pasan eval
            </>
          )}
        </div>
        {metaHit > 0 && (
          <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
            {metaHit} mes(es) superan +${WS_META_USD}
          </div>
        )}
      </div>
      <div>
        <div className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--text-faint)" }}>
          Suma del rango*
        </div>
        <div className="font-semibold tabular-nums" style={{ color: totalPnl >= 0 ? "var(--green)" : "var(--red)" }}>
          {totalPnl >= 0 ? "+" : ""}
          {formatCurrency(totalPnl)}
        </div>
        <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
          Mejor: {best.label} ({formatCurrency(best.total_pnl ?? 0)})
        </div>
      </div>
      <div>
        <div className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--text-faint)" }}>
          Peor mes · {totalTrades} trades
        </div>
        <div style={{ color: "var(--red)" }}>
          {worst.label}: {formatCurrency(worst.total_pnl ?? 0)}
        </div>
        <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
          Cada mes = eval nueva de $5k
        </div>
      </div>
      <p className="sm:col-span-2 lg:col-span-4 text-[10px]" style={{ color: "var(--text-faint)" }}>
        *Cada mes arranca con $5,000. “Rentable” no es lo mismo que “Pasa eval” (+$400 y todas las reglas). La estrategia se usa reintentando evals ~2–3 meses.
      </p>
    </div>
  );
}

function MonthCard({
  row,
  onSelect,
  highlight = false,
  selected = false,
}: {
  row: MonthlyRow;
  onSelect: () => void;
  highlight?: boolean;
  selected?: boolean;
}) {
  if (row.error) {
    return (
      <div className="rounded-lg p-3 text-xs opacity-60" style={{ background: "var(--bg-hover)" }}>
        <div className="font-medium">{row.label}</div>
        <div style={{ color: "var(--text-faint)" }}>
          {row.error === "failed" ? "Error al simular" : "Sin datos suficientes"}
        </div>
      </div>
    );
  }
  const pass = row.pass_eval;
  const badge = monthEvalBadge(row.total_pnl, pass);
  const detail = monthEvalDetail(row.total_pnl, row.fail_reasons);
  const badgeColors: Record<string, { color: string; bg: string }> = {
    pass: { color: "var(--green)", bg: "color-mix(in srgb, var(--green) 15%, transparent)" },
    good: { color: "var(--green)", bg: "color-mix(in srgb, var(--green) 12%, transparent)" },
    warn: { color: "#b8860b", bg: "color-mix(in srgb, #b8860b 15%, transparent)" },
    bad: { color: "var(--red)", bg: "color-mix(in srgb, var(--red) 15%, transparent)" },
  };
  const bc = badgeColors[badge.tone];
  return (
    <button
      type="button"
      onClick={onSelect}
      className="rounded-lg p-3 text-left transition-opacity hover:opacity-90 w-full border"
      style={{
        background: highlight ? "color-mix(in srgb, var(--accent) 10%, var(--bg-hover))" : "var(--bg-hover)",
        borderColor: selected
          ? "var(--accent)"
          : badge.tone === "pass" || badge.tone === "good"
            ? "color-mix(in srgb, var(--green) 40%, transparent)"
            : "var(--border)",
        boxShadow: selected ? "0 0 0 1px var(--accent)" : undefined,
      }}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="text-sm font-semibold" style={{ color: "var(--text)" }}>{row.label}</div>
        <span
          className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded shrink-0"
          style={{ color: bc.color, background: bc.bg }}
        >
          {badge.label}
        </span>
      </div>
      <div
        className="text-lg font-semibold tabular-nums"
        style={{ color: (row.total_pnl ?? 0) >= 0 ? "var(--green)" : "var(--red)" }}
      >
        {(row.total_pnl ?? 0) >= 0 ? "+" : ""}{formatCurrency(row.total_pnl ?? 0)}
        <span className="text-xs font-normal ml-1" style={{ color: "var(--text-muted)" }}>
          ({(row.total_pnl_pct ?? 0) >= 0 ? "+" : ""}{row.total_pnl_pct}%)
        </span>
      </div>
      <div className="text-xs mt-2 space-y-0.5" style={{ color: "var(--text-muted)" }}>
        <div>{row.trades} trades · WR {row.win_rate_pct?.toFixed(0)}%</div>
        <div>DD {row.static_dd_pct}% · día {row.max_daily_loss_pct}%</div>
        {row.days_to_meta != null && pass && (
          <div style={{ color: "var(--green)" }}>Meta en {row.days_to_meta}d</div>
        )}
        {detail && (
          <div style={{ color: badge.tone === "bad" ? "var(--red)" : "var(--text-muted)" }}>{detail}</div>
        )}
        {!pass && (row.total_pnl ?? 0) > 0 && (row.total_pnl ?? 0) < WS_META_USD && (
          <div className="h-1.5 rounded-full overflow-hidden mt-1" style={{ background: "var(--border)" }}>
            <div
              className="h-full rounded-full"
              style={{
                width: `${metaProgressPct(row.total_pnl ?? 0)}%`,
                background: "var(--green)",
              }}
            />
          </div>
        )}
      </div>
      <div className="text-[10px] mt-2" style={{ color: "var(--text-faint)" }}>
        {row.period_start} → {row.period_end}
      </div>
    </button>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: "var(--text)" }}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

export default function LiquiditySweepPage() {
  return (
    <Suspense fallback={<div className="p-8" style={{ color: "var(--text-muted)" }}>Cargando simulador…</div>}>
      <LiquiditySweepPageInner />
    </Suspense>
  );
}
