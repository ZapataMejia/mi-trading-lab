"use client";

import { OnlineNotice } from "./OnlineNotice";

/** Contenedor del área principal (sin barra extra duplicada) */
export function MainChrome({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex-1 min-w-0 flex flex-col">
      <OnlineNotice />
      <main className="flex-1 min-w-0 overflow-x-hidden">{children}</main>
    </div>
  );
}
