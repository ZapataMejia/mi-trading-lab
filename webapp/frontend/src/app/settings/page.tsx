"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useTheme } from "@/components/ThemeProvider";
import { useToast } from "@/components/Toast";

export default function SettingsPage() {
  const { theme, toggle } = useTheme();
  const [info, setInfo] = useState<Record<string, unknown> | null>(null);
  const toast = useToast();

  useEffect(() => {
    api.dataInfo().then(setInfo).catch(() => null);
  }, []);

  function clearCache() {
    sessionStorage.clear();
    toast.push("Cache limpiado", "success");
  }

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <h1 className="text-2xl font-semibold tracking-tight mb-6" style={{ color: "var(--text)" }}>
        Configuración
      </h1>

      <Group title="Apariencia">
        <Row label="Tema" hint={theme === "dark" ? "Modo oscuro activo" : "Modo claro activo"}>
          <button onClick={toggle} className="btn-secondary">
            Cambiar a {theme === "light" ? "oscuro" : "claro"}
          </button>
        </Row>
      </Group>

      <Group title="Datos">
        <Row label="Cache de resultados (sessionStorage)" hint="Limpia los backtests cacheados de esta sesión">
          <button onClick={clearCache} className="btn-secondary">
            Limpiar cache
          </button>
        </Row>
        {info && (
          <div className="mt-3 text-xs" style={{ color: "var(--text-muted)" }}>
            <strong>Datasets disponibles:</strong>
            <pre
              className="mt-2 p-3 rounded-md overflow-x-auto"
              style={{ background: "var(--bg-hover)", color: "var(--text)" }}
            >
              {JSON.stringify(info, null, 2)}
            </pre>
          </div>
        )}
      </Group>

      <Group title="Backend">
        <Row label="API base URL" hint="Para correr el backend en otra máquina, edita NEXT_PUBLIC_API_BASE">
          <code className="text-xs px-2 py-1 rounded" style={{ background: "var(--bg-hover)", color: "var(--text)" }}>
            http://localhost:8000
          </code>
        </Row>
        <Row label="API docs" hint="Documentación interactiva del backend">
          <a className="btn-secondary inline-block" href="http://localhost:8000/docs" target="_blank">
            Abrir /docs
          </a>
        </Row>
      </Group>
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="card p-5 mb-4">
      <h2 className="text-sm font-semibold uppercase tracking-wider mb-3" style={{ color: "var(--text-muted)" }}>
        {title}
      </h2>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <div>
        <div className="text-sm font-medium" style={{ color: "var(--text)" }}>
          {label}
        </div>
        {hint && (
          <div className="text-xs mt-0.5" style={{ color: "var(--text-faint)" }}>
            {hint}
          </div>
        )}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}
