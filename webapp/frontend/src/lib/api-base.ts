/** URL del backend FastAPI. */
const PRODUCTION_API = "https://mitradinglab.pythonanywhere.com";

export function getApiBase(): string {
  const fromEnv = process.env.NEXT_PUBLIC_API_BASE?.trim();
  if (fromEnv) return fromEnv.replace(/\/$/, "");

  if (typeof window !== "undefined") {
    const { hostname } = window.location;
    // Desplegado en Vercel → siempre PythonAnywhere (aunque falte la env var)
    if (hostname.endsWith(".vercel.app") || hostname.includes("vercel.app")) {
      return PRODUCTION_API;
    }
    if (hostname === "localhost" || hostname === "127.0.0.1") {
      return "http://localhost:8000";
    }
    return `http://${hostname}:8000`;
  }

  return PRODUCTION_API;
}
