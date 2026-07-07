"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Strategy } from "@/lib/types";
import { Layers, LineChart, FlaskConical, FileText, Settings, Search, Target, TrendingUp } from "lucide-react";

interface Command {
  id: string;
  label: string;
  hint?: string;
  group: string;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>;
  action: () => void;
}

const STATIC_COMMANDS_FACTORY = (router: ReturnType<typeof useRouter>): Command[] => [
  { id: "go-sim", label: "Simulador WS", hint: "Liquidity Sweep · EURUSD M5", group: "Páginas", icon: Target, action: () => router.push("/fondeo/liquidity-sweep") },
  { id: "go-curso", label: "Curso · EMA Cross", hint: "Estrategia del mentoring + hedge 2 cuentas", group: "Páginas", icon: TrendingUp, action: () => router.push("/fondeo") },
  { id: "go-home", label: "Estrategias", hint: "Ver lista de estrategias", group: "Páginas", icon: Layers, action: () => router.push("/") },
  { id: "go-compare", label: "Comparar estrategias", hint: "Side-by-side de 2-6 estrategias", group: "Páginas", icon: LineChart, action: () => router.push("/compare") },
  { id: "go-lab", label: "Laboratorio", hint: "Walk-forward y grid search", group: "Páginas", icon: FlaskConical, action: () => router.push("/lab") },
  { id: "go-docs", label: "Guía", hint: "Cómo usar el simulador", group: "Páginas", icon: FileText, action: () => router.push("/docs") },
  { id: "go-settings", label: "Configuración", hint: "Tema, etc.", group: "Páginas", icon: Settings, action: () => router.push("/settings") },
];

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [active, setActive] = useState(0);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
        setQ("");
        setActive(0);
      } else if (e.key === "Escape" && open) {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    if (open && strategies.length === 0) {
      api.listStrategies().then((r) => setStrategies(r.strategies)).catch(() => null);
    }
  }, [open, strategies.length]);

  const commands = useMemo(() => {
    const stat = STATIC_COMMANDS_FACTORY(router);
    const stratCmds: Command[] = strategies.map((s) => ({
      id: `strat-${s.id}`,
      label: s.name,
      hint: s.description.slice(0, 80),
      group: "Estrategias",
      icon: Layers,
      action: () => router.push(`/strategies/${encodeURIComponent(s.id)}`),
    }));
    return [...stat, ...stratCmds];
  }, [router, strategies]);

  const filtered = useMemo(() => {
    if (!q) return commands;
    const needle = q.toLowerCase();
    return commands.filter((c) => c.label.toLowerCase().includes(needle) || (c.hint || "").toLowerCase().includes(needle));
  }, [q, commands]);

  useEffect(() => {
    setActive(0);
  }, [q]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(filtered.length - 1, a + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(0, a - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const c = filtered[active];
      if (c) {
        c.action();
        setOpen(false);
      }
    }
  }

  if (!open) return null;

  // group commands
  const grouped = filtered.reduce<Record<string, Command[]>>((acc, c) => {
    (acc[c.group] ||= []).push(c);
    return acc;
  }, {});

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh] px-4"
      style={{ background: "rgba(0,0,0,0.45)", backdropFilter: "blur(2px)" }}
      onClick={() => setOpen(false)}
    >
      <div
        className="w-full max-w-xl rounded-xl overflow-hidden shadow-2xl"
        style={{ background: "var(--bg-card)", border: "1px solid var(--border-strong)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 px-3 py-2.5 border-b" style={{ borderColor: "var(--border)" }}>
          <Search size={16} strokeWidth={1.75} style={{ color: "var(--text-muted)" }} />
          <input
            type="text"
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Buscar estrategias, páginas, comandos…"
            className="flex-1 bg-transparent outline-none border-none text-sm py-1"
            style={{ color: "var(--text)" }}
          />
          <span className="text-xs" style={{ color: "var(--text-faint)" }}>
            esc
          </span>
        </div>
        <div className="max-h-[60vh] overflow-y-auto py-2">
          {filtered.length === 0 ? (
            <div className="px-4 py-6 text-sm text-center" style={{ color: "var(--text-faint)" }}>
              Sin resultados
            </div>
          ) : (
            Object.entries(grouped).map(([group, items]) => (
              <div key={group} className="mb-1">
                <div className="px-3 py-1 text-[10px] uppercase tracking-wider" style={{ color: "var(--text-faint)" }}>
                  {group}
                </div>
                {items.map((c) => {
                  const isActive = filtered.indexOf(c) === active;
                  return (
                    <button
                      key={c.id}
                      onClick={() => { c.action(); setOpen(false); }}
                      onMouseEnter={() => setActive(filtered.indexOf(c))}
                      className="w-full flex items-center gap-3 px-3 py-2 text-left transition-colors"
                      style={{
                        background: isActive ? "var(--bg-active)" : "transparent",
                        color: "var(--text)",
                      }}
                    >
                      <c.icon size={15} strokeWidth={1.75} />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm">{c.label}</div>
                        {c.hint && (
                          <div className="text-xs truncate" style={{ color: "var(--text-faint)" }}>
                            {c.hint}
                          </div>
                        )}
                      </div>
                      {isActive && (
                        <span className="text-xs" style={{ color: "var(--text-faint)" }}>
                          ↵
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
        <div className="px-3 py-2 text-xs border-t flex items-center justify-between" style={{ borderColor: "var(--border)", color: "var(--text-faint)" }}>
          <span>↑↓ navegar · ↵ abrir · esc cerrar</span>
          <span>⌘K</span>
        </div>
      </div>
    </div>
  );
}
