/** Meta WS Funded fase 1 — cuenta $5k */
export const WS_META_USD = 400;

/** Precomputado con scripts/eval_timing_safe.py (histórico 2017–2024, config SAFE). */
export const LIQ_SWEEP_TIMING = {
  medianDaysWhenPasses: 9,
  passRate30dPct: 41.2,
  expectedAttempts: 2.43,
  estimatedMonthsLabel: "~2–3 meses",
  probTwoAccountsPct: 65.4,
  dataNote: "Histórico EURUSD 2017–2024 · misma config del simulador",
} as const;

export function metaProgressPct(pnl: number): number {
  if (pnl <= 0) return 0;
  return Math.min(100, Math.round((pnl / WS_META_USD) * 100));
}

export type MonthEvalTone = "pass" | "good" | "warn" | "bad";

export function monthEvalBadge(pnl: number | undefined, passEval: boolean | undefined): { label: string; tone: MonthEvalTone } {
  if (passEval) return { label: "Pasa eval", tone: "pass" };
  const v = pnl ?? 0;
  if (v >= WS_META_USD) return { label: "Meta alcanzada", tone: "warn" };
  if (v > 0) return { label: "Rentable", tone: "good" };
  return { label: "Pierde", tone: "bad" };
}

export function monthEvalDetail(pnl: number | undefined, failReasons: string[] | undefined): string | null {
  const v = pnl ?? 0;
  if (v > 0 && v < WS_META_USD && failReasons?.includes("meta")) {
    return `Meta eval: ${metaProgressPct(v)}% ($${Math.round(v)} / $${WS_META_USD})`;
  }
  if (failReasons?.length && v >= WS_META_USD) {
    return `Meta OK · revisar: ${failReasons.filter((r) => r !== "meta").join(", ") || "reglas"}`;
  }
  if (failReasons?.length && v <= 0) {
    return failReasons.includes("meta") ? "No alcanzó la meta del mes" : `Falla: ${failReasons.join(", ")}`;
  }
  return null;
}
