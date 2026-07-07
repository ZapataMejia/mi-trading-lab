/** Mensaje legible para errores de red / API en la UI. */
export function fetchErrorMessage(err: unknown): string {
  if (err instanceof DOMException && err.name === "AbortError") {
    return "La simulación tardó demasiado (~1 min). Elige un periodo más corto (máx. 3 meses en la nube).";
  }
  const msg = String(err);
  if (msg.includes("Failed to fetch") || msg.includes("NetworkError")) {
    return "No se pudo conectar con el servidor. Espera unos segundos e inténtalo de nuevo.";
  }
  if (msg.includes("429") || msg.includes("simulación en curso")) {
    return "El servidor está ocupado. Espera unos segundos e inténtalo otra vez.";
  }
  if (msg.includes("504") || msg.includes("502")) {
    return "El servidor tardó demasiado. Prueba un periodo más corto (ej. Ene–Mar 2026).";
  }
  return msg.replace(/^Error:\s*/, "").slice(0, 240);
}

/** Ping al backend (PythonAnywhere free duerme). */
export async function waitForBackend(
  apiBase: string,
  { attempts = 4, delayMs = 2000 }: { attempts?: number; delayMs?: number } = {},
): Promise<boolean> {
  for (let i = 0; i < attempts; i += 1) {
    try {
      const res = await fetch(`${apiBase}/api/health`, { cache: "no-store" });
      if (res.ok) return true;
    } catch {
      /* retry */
    }
    if (i < attempts - 1) await new Promise((r) => setTimeout(r, delayMs));
  }
  return false;
}
