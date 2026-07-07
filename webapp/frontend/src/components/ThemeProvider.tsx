"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

type Theme = "light" | "dark";

const ThemeCtx = createContext<{ theme: Theme; toggle: () => void; mounted: boolean } | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // El inline script en layout.tsx ya seteo el data-theme correcto antes del
  // primer paint. Acá leemos lo que dejo en el DOM (matches localStorage) para
  // que el state inicial este alineado y no haya hydration mismatch.
  const [theme, setTheme] = useState<Theme>("light");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const fromDom = document.documentElement.getAttribute("data-theme") as Theme | null;
    if (fromDom === "dark" || fromDom === "light") setTheme(fromDom);
    setMounted(true);
  }, []);

  function toggle() {
    setTheme((cur) => {
      const next: Theme = cur === "light" ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("theme", next);
      return next;
    });
  }

  return <ThemeCtx.Provider value={{ theme, toggle, mounted }}>{children}</ThemeCtx.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeCtx);
  if (!ctx) throw new Error("useTheme must be used inside ThemeProvider");
  return ctx;
}

export function ThemeToggle() {
  const { theme, toggle, mounted } = useTheme();
  if (!mounted) {
    return <span className="btn-ghost inline-flex items-center gap-2" aria-hidden style={{ width: 32, height: 28 }} />;
  }
  return (
    <button
      onClick={toggle}
      className="btn-ghost inline-flex items-center gap-2"
      title={`Cambiar a ${theme === "light" ? "dark" : "light"} mode`}
    >
      {theme === "light" ? <Moon size={15} strokeWidth={1.75} /> : <Sun size={15} strokeWidth={1.75} />}
    </button>
  );
}
