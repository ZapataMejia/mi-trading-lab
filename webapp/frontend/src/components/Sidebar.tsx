"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  FlaskConical,
  LineChart,
  Layers,
  FileText,
  Settings,
  Command,
  TrendingUp,
  Target,
} from "lucide-react";
import { ThemeToggle } from "./ThemeProvider";
import { SidebarToggleButton, useSidebar } from "./SidebarContext";

const NAV = [
  { href: "/fondeo/liquidity-sweep", label: "Simulador WS ★", icon: Target },
  { href: "/fondeo", label: "Curso · EMA Cross", icon: TrendingUp },
  { href: "/", label: "Estrategias", icon: Layers },
  { href: "/compare", label: "Comparar", icon: LineChart },
  { href: "/lab", label: "Laboratorio", icon: FlaskConical },
  { href: "/docs", label: "Guía", icon: FileText },
];

export function Sidebar() {
  const pathname = usePathname();
  const { collapsed } = useSidebar();
  const narrow = collapsed;

  return (
    <aside
      className="shrink-0 border-r flex flex-col transition-[width] duration-200 overflow-hidden"
      style={{
        width: narrow ? 56 : 240,
        background: "var(--bg-sidebar)",
        borderColor: "var(--border)",
      }}
    >
      {narrow ? (
        <div className="flex flex-col items-center gap-2 py-3 px-1 border-b" style={{ borderColor: "var(--border)" }}>
          <SidebarToggleButton showWhen="always" className="border-0 bg-transparent p-2" />
        </div>
      ) : (
        <div className="px-3 py-4 border-b flex items-center gap-2" style={{ borderColor: "var(--border)" }}>
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center font-bold text-white text-sm shrink-0"
            style={{ background: "var(--accent)" }}
          >
            ML
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-semibold text-sm truncate" style={{ color: "var(--text)" }}>
              Mi Trading Lab
            </div>
            <div className="text-xs truncate" style={{ color: "var(--text-faint)" }}>
              Simulador en línea
            </div>
          </div>
          <ThemeToggle />
          <SidebarToggleButton showWhen="always" className="border-0 bg-transparent p-1.5" />
        </div>
      )}

      <nav className="flex-1 px-1.5 py-3 flex flex-col gap-0.5 overflow-y-auto">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active =
            href === "/"
              ? pathname === "/"
              : href === "/fondeo"
                ? pathname === "/fondeo"
                : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              title={narrow ? label : undefined}
              className="flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm transition-colors"
              style={{
                color: active ? "var(--text)" : "var(--text-muted)",
                background: active ? "var(--bg-active)" : "transparent",
                fontWeight: active ? 500 : 400,
                justifyContent: narrow ? "center" : "flex-start",
              }}
            >
              <Icon size={16} strokeWidth={1.75} className="shrink-0" />
              {!narrow && <span className="truncate">{label}</span>}
              {narrow && <span className="sr-only">{label}</span>}
            </Link>
          );
        })}
      </nav>

      <div className="p-2 border-t flex flex-col gap-0.5" style={{ borderColor: "var(--border)" }}>
        {!narrow && (
          <div
            className="flex items-center justify-between gap-2 px-2.5 py-2 rounded-md text-xs"
            style={{ color: "var(--text-faint)" }}
          >
            <span className="inline-flex items-center gap-1.5">
              <Command size={12} strokeWidth={1.75} />
              Buscador
            </span>
            <span className="font-mono">⌘K</span>
          </div>
        )}
        <Link
          href="/settings"
          title={narrow ? "Configuración" : undefined}
          className="flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm"
          style={{
            color: "var(--text-muted)",
            justifyContent: narrow ? "center" : "flex-start",
          }}
        >
          <Settings size={16} strokeWidth={1.75} className="shrink-0" />
          {!narrow && "Configuración"}
        </Link>
        {narrow && (
          <div className="flex justify-center py-1">
            <ThemeToggle />
          </div>
        )}
      </div>
    </aside>
  );
}
