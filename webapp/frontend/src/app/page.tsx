"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Strategy } from "@/lib/types";
import { StrategyCard } from "@/components/StrategyCard";
import { useToast } from "@/components/Toast";
import { useCapabilities } from "@/components/CapabilitiesProvider";
import { marketBacktestAvailable } from "@/lib/capabilities";
import { RefreshCcw, Plus, Search } from "lucide-react";

export default function HomePage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [reloading, setReloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const toast = useToast();
  const caps = useCapabilities();
  const limitedOnline = !caps.polymarket || !caps.crypto;

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const r = await api.listStrategies();
      setStrategies(r.strategies);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function reload() {
    setReloading(true);
    try {
      const r = await api.reloadStrategies();
      toast.push(`${r.loaded} estrategias cargadas`, "success");
      await load();
    } catch (e) {
      toast.push(`Error al recargar: ${String(e)}`, "error");
    } finally {
      setReloading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    if (!q) return strategies;
    const needle = q.toLowerCase();
    return strategies.filter(
      (s) =>
        s.name.toLowerCase().includes(needle) ||
        s.description.toLowerCase().includes(needle) ||
        s.tags.some((t) => t.toLowerCase().includes(needle)) ||
        s.market_type.toLowerCase().includes(needle),
    );
  }, [q, strategies]);

  const grouped = useMemo(() => {
    return filtered.reduce<Record<string, Strategy[]>>((acc, s) => {
      (acc[s.market_type] ||= []).push(s);
      return acc;
    }, {});
  }, [filtered]);

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <header className="flex items-end justify-between mb-7 gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight" style={{ color: "var(--text)" }}>
            Estrategias
          </h1>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
            {filtered.length} {filtered.length === 1 ? "disponible" : "disponibles"}
            {q && ` (de ${strategies.length})`}
            {limitedOnline
              ? " · Polymarket/crypto solo en versión local"
              : " · backtesteables al instante"}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative">
            <Search
              size={14}
              strokeWidth={1.75}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none"
              style={{ color: "var(--text-faint)" }}
            />
            <input
              type="text"
              placeholder="Buscar..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="pl-8 w-[180px]"
            />
          </div>
          <button onClick={reload} disabled={reloading} className="btn-secondary inline-flex items-center gap-2">
            <RefreshCcw size={14} strokeWidth={1.75} className={reloading ? "animate-spin" : ""} />
            Recargar
          </button>
          <button onClick={() => (window.location.href = "/docs")} className="btn-primary inline-flex items-center gap-2">
            <Plus size={14} strokeWidth={2} />
            Nueva
          </button>
        </div>
      </header>

      {error && (
        <div
          className="card p-4 mb-6 text-sm"
          style={{ background: "var(--red-light)", borderColor: "var(--red)", color: "var(--red)" }}
        >
          <strong>Error al conectar con el backend:</strong> {error}
          <div className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
            {typeof window !== "undefined" && window.location.hostname.includes("vercel.app")
              ? "El servidor en la nube puede tardar unos segundos en despertar. Pulsa Recargar."
              : "Verifica que uvicorn webapp.backend.main:app --port 8000 esté corriendo en local."}
          </div>
        </div>
      )}

      {loading ? (
        <div className="grid md:grid-cols-2 gap-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="card p-5 h-[170px] animate-pulse" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="card p-12 text-center text-sm" style={{ color: "var(--text-faint)" }}>
          {q ? "No hay estrategias que coincidan con la busqueda" : "Sin estrategias cargadas"}
        </div>
      ) : (
        <div className="space-y-8">
          {Object.entries(grouped).map(([market, list]) => (
            <section key={market}>
              <div className="flex items-baseline gap-2 mb-3">
                <h2 className="text-sm font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                  {market === "polymarket" ? "Polymarket" : market === "crypto_perp" ? "Crypto Perp" : market}
                </h2>
                <span className="text-xs" style={{ color: "var(--text-faint)" }}>
                  · {list.length}
                </span>
              </div>
              <div className="grid md:grid-cols-2 gap-3">
                {list.map((s) => (
                  <StrategyCard
                    key={s.id}
                    strategy={s}
                    backtestDisabled={!marketBacktestAvailable(caps, s.market_type)}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
