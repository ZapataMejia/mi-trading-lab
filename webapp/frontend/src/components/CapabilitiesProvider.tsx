"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { fetchCapabilities, type Capabilities } from "@/lib/capabilities";

const CapabilitiesContext = createContext<Capabilities | null>(null);

export function CapabilitiesProvider({ children }: { children: React.ReactNode }) {
  const [caps, setCaps] = useState<Capabilities | null>(null);

  useEffect(() => {
    fetchCapabilities().then(setCaps);
  }, []);

  return (
    <CapabilitiesContext.Provider value={caps}>{children}</CapabilitiesContext.Provider>
  );
}

export function useCapabilities(): Capabilities {
  const ctx = useContext(CapabilitiesContext);
  return (
    ctx ?? {
      forex: true,
      polymarket: true,
      crypto: true,
      online_mode: false,
      max_sim_days: 400,
    }
  );
}

export function useCapabilitiesReady(): boolean {
  return useContext(CapabilitiesContext) !== null;
}
