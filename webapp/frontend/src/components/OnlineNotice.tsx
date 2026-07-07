"use client";

import Link from "next/link";
import { AlertCircle, Target } from "lucide-react";
import { useCapabilities } from "./CapabilitiesProvider";

/** Aviso global cuando Polymarket/crypto no están disponibles en este servidor */
export function OnlineNotice() {
  const caps = useCapabilities();
  const limited = !caps.polymarket || !caps.crypto;

  if (!limited) return null;

  return (
    <div
      className="mx-4 mt-4 mb-0 px-4 py-3 rounded-lg border text-sm flex items-start gap-3"
      style={{
        background: "color-mix(in srgb, var(--accent) 8%, var(--bg-card))",
        borderColor: "var(--border)",
        color: "var(--text-muted)",
      }}
    >
      <AlertCircle size={18} className="shrink-0 mt-0.5" style={{ color: "var(--accent)" }} />
      <div>
        <p className="font-medium mb-1" style={{ color: "var(--text)" }}>
          Versión en línea · simulador forex
        </p>
        <p>
          En este servidor funcionan el{" "}
          <Link href="/fondeo/liquidity-sweep" className="underline inline-flex items-center gap-1" style={{ color: "var(--accent)" }}>
            <Target size={14} /> Simulador WS
          </Link>{" "}
          y el{" "}
          <Link href="/fondeo" className="underline" style={{ color: "var(--accent)" }}>
            Curso EMA Cross
          </Link>
          .{" "}
          {!caps.polymarket && !caps.crypto
            ? "Comparar, Estrategias (Polymarket/crypto) y Lab avanzado requieren datos que solo están en la versión local."
            : !caps.polymarket
              ? "Backtests de Polymarket no están disponibles aquí."
              : "Backtests crypto (Binance) no están disponibles aquí."}
        </p>
      </div>
    </div>
  );
}
