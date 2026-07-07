import { getApiBase } from "./api-base";

export type Capabilities = {
  forex: boolean;
  polymarket: boolean;
  crypto: boolean;
  online_mode: boolean;
  max_sim_days: number;
};

const DEFAULTS: Capabilities = {
  forex: true,
  polymarket: true,
  crypto: true,
  online_mode: false,
  max_sim_days: 400,
};

let cache: Capabilities | null = null;

export async function fetchCapabilities(force = false): Promise<Capabilities> {
  if (cache && !force) return cache;
  const base = getApiBase();
  try {
    const res = await fetch(`${base}/api/capabilities`, { cache: "no-store" });
    if (res.status === 404 && base.includes("pythonanywhere.com")) {
      cache = { forex: true, polymarket: false, crypto: false, online_mode: true, max_sim_days: 90 };
      return cache;
    }
    if (!res.ok) throw new Error(String(res.status));
    const raw = await res.json();
    const data = {
      ...DEFAULTS,
      ...raw,
      max_sim_days: typeof raw.max_sim_days === "number" && raw.max_sim_days > 0 ? raw.max_sim_days : DEFAULTS.max_sim_days,
    } as Capabilities;
    cache = data;
    return data;
  } catch {
    if (base.includes("pythonanywhere.com") || (typeof window !== "undefined" && window.location.hostname.includes("vercel.app"))) {
      cache = { forex: true, polymarket: false, crypto: false, online_mode: true, max_sim_days: 90 };
      return cache;
    }
    return DEFAULTS;
  }
}

export function marketBacktestAvailable(caps: Capabilities, marketType: string): boolean {
  if (marketType === "polymarket") return caps.polymarket;
  if (marketType === "crypto_perp") return caps.crypto;
  return caps.polymarket || caps.crypto;
}

export function anyPolyOrCrypto(caps: Capabilities): boolean {
  return caps.polymarket || caps.crypto;
}
