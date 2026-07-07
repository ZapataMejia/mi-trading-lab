"use client";

import Link from "next/link";
import { FileText, Target, TrendingUp, LineChart, FlaskConical, ArrowRight } from "lucide-react";

export default function DocsPage() {
  return (
    <div className="p-8 max-w-3xl mx-auto">
      <h1 className="text-2xl font-semibold tracking-tight mb-2" style={{ color: "var(--text)" }}>
        Guía de uso
      </h1>
      <p className="text-sm mb-8" style={{ color: "var(--text-muted)" }}>
        Cómo usar Mi Trading Lab paso a paso. Empieza por el simulador; el resto es opcional.
      </p>

      <Section icon={Target} title="1. Simulador WS (Liquidity Sweep)">
        <p className="mb-3">
          Es la pantalla principal. Simula la estrategia <strong>Liquidity Sweep</strong> en EURUSD con velas de{" "}
          <strong>5 minutos (M5)</strong> — la única temporalidad con datos en el servidor.
        </p>
        <ol className="list-decimal pl-5 space-y-2 mb-4">
          <li>Abre <strong>Simulador WS ★</strong> en el menú izquierdo.</li>
          <li>Elige <strong>desde</strong> y <strong>hasta</strong> con el calendario (cualquier rango dentro de los datos disponibles).</li>
          <li>Pulsa <strong>Simular este periodo</strong> (máx. ~90 días por simulación).</li>
          <li>Para un <strong>año entero</strong>, usa el bloque <strong>“Simular año mes a mes”</strong> justo debajo.</li>
          <li>Revisa si <strong>pasa la evaluación WS</strong> ($5,000, meta +8%).</li>
          <li>Opcional: “Cargar gráfico” en periodos cortos (≤ 45 días).</li>
        </ol>
        <p className="text-xs mb-4" style={{ color: "var(--text-faint)" }}>
          El rango disponible lo muestra el cuadro azul arriba (mismo histórico Dukascopy que en local, desde 2003 si el servidor tiene el archivo completo).
        </p>
        <Link href="/fondeo/liquidity-sweep?preset=q1-2026" className="btn-primary inline-flex items-center gap-2 text-sm">
          Abrir simulador
          <ArrowRight size={14} />
        </Link>
      </Section>

      <Section icon={TrendingUp} title="2. Curso · EMA Cross">
        <p className="mb-3">
          Estrategia del <strong>Programa de Mentorías para Traders Algorítmicos</strong> (HobbyCode / AlgoWizard):
          cruce EMA 9 y 18 en EURUSD M5, sesión Londres, riesgo ~2,1%.
        </p>
        <p className="mb-3">
          Para fondeo WS recomiendan <strong>dos cuentas de $5,000</strong>: una sigue la señal y la otra hace lo
          contrario (hedge). Abajo en esa página puedes simular ese par.
        </p>
        <Link href="/fondeo" className="btn-secondary inline-flex items-center gap-2 text-sm">
          Ir al curso EMA
          <ArrowRight size={14} />
        </Link>
      </Section>

      <Section icon={LineChart} title="3. Comparar estrategias (solo versión local)">
        <p>
          En la nube no está disponible (faltan datos Polymarket/crypto). En local puedes elegir 2 a 6 estrategias y
          compararlas en el mismo periodo.
        </p>
      </Section>

      <Section icon={FlaskConical} title="4. Laboratorio (solo versión local)">
        <p>
          Walk-forward y grid search para bots de Polymarket — solo en local. Para forex WS usa siempre el{" "}
          <Link href="/fondeo/liquidity-sweep" className="underline" style={{ color: "var(--accent)" }}>
            simulador
          </Link>
          .
        </p>
      </Section>

      <Section icon={FileText} title="Consejos">
        <ul className="space-y-2 list-disc pl-5">
          <li>Si ves “Failed to fetch” o error de conexión, espera unos segundos y vuelve a pulsar Simular.</li>
          <li>Los datos van desde <strong>2003</strong> (histórico Dukascopy M5) si el servidor tiene el archivo completo instalado.</li>
          <li>El atajo <span className="font-mono text-xs px-1 rounded" style={{ background: "var(--bg-hover)" }}>⌘K</span> abre el buscador rápido.</li>
          <li>Periodos largos: usa <strong>mes a mes</strong> o trozos de hasta 3 meses (~90 días).</li>
        </ul>
      </Section>
    </div>
  );
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="card p-5 mb-4">
      <h2 className="text-base font-semibold mb-3 inline-flex items-center gap-2" style={{ color: "var(--text)" }}>
        <Icon size={16} strokeWidth={1.75} />
        {title}
      </h2>
      <div className="text-sm" style={{ color: "var(--text-muted)" }}>
        {children}
      </div>
    </section>
  );
}
