"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";

const STORAGE_KEY = "sidebar-collapsed";

type SidebarContextValue = {
  collapsed: boolean;
  toggle: () => void;
  mounted: boolean;
};

const SidebarContext = createContext<SidebarContextValue | null>(null);

export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof document === "undefined") return false;
    try {
      return (
        localStorage.getItem(STORAGE_KEY) === "1" ||
        document.documentElement.getAttribute("data-sidebar-collapsed") === "1"
      );
    } catch {
      return false;
    }
  });
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    try {
      setCollapsed(localStorage.getItem(STORAGE_KEY) === "1");
    } catch {
      /* ignore */
    }
    setMounted(true);
  }, []);

  const toggle = useCallback(() => {
    setCollapsed((c) => {
      const next = !c;
      try {
        localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  return (
    <SidebarContext.Provider value={{ collapsed, toggle, mounted }}>
      {children}
    </SidebarContext.Provider>
  );
}

export function useSidebar() {
  const ctx = useContext(SidebarContext);
  if (!ctx) throw new Error("useSidebar must be used within SidebarProvider");
  return ctx;
}

/** Botón para abrir/cerrar menú — visible en sidebar expandido y barra superior cuando está colapsado */
export function SidebarToggleButton({
  className = "",
  showWhen = "always",
}: {
  className?: string;
  showWhen?: "always" | "collapsed" | "expanded";
}) {
  const { collapsed, toggle } = useSidebar();

  if (showWhen === "collapsed" && !collapsed) return null;
  if (showWhen === "expanded" && collapsed) return null;

  return (
    <button
      type="button"
      onClick={toggle}
      className={`p-2 rounded-md border inline-flex items-center justify-center shrink-0 ${className}`}
      style={{
        color: "var(--text-muted)",
        borderColor: "var(--border)",
        background: "var(--bg-card)",
      }}
      title={collapsed ? "Abrir menú" : "Ocultar menú"}
      aria-label={collapsed ? "Abrir menú" : "Ocultar menú"}
    >
      {collapsed ? <PanelLeftOpen size={18} strokeWidth={1.75} /> : <PanelLeftClose size={18} strokeWidth={1.75} />}
    </button>
  );
}
