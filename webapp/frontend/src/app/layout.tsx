import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { SidebarProvider } from "@/components/SidebarContext";
import { MainChrome } from "@/components/MainChrome";
import { CapabilitiesProvider } from "@/components/CapabilitiesProvider";
import { ThemeProvider } from "@/components/ThemeProvider";
import { ToastProvider } from "@/components/Toast";
import { CommandPalette } from "@/components/CommandPalette";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Mi Trading Lab",
  description: "Backtester local de estrategias — Polymarket, crypto, options",
};

// Script inline que corre durante el parseo del HTML — antes del primer paint —
// para aplicar el theme guardado en localStorage. Evita el flash de light → dark
// y la hydration mismatch que estaba acumulando "issues" en dev tools.
// Patron recomendado en la doc oficial de Next.js 16:
// node_modules/next/dist/docs/01-app/02-guides/preventing-flash-before-hydration.md
const themeInitScript = `(function(){try{var t=localStorage.getItem("theme");if(!t){t=window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.setAttribute("data-theme",t)}catch(e){}})()`;
const sidebarInitScript = `(function(){try{var c=localStorage.getItem("sidebar-collapsed");if(c==="1")document.documentElement.setAttribute("data-sidebar-collapsed","1")}catch(e){}})()`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" data-theme="light" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        <script dangerouslySetInnerHTML={{ __html: sidebarInitScript }} />
      </head>
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        <ThemeProvider>
          <ToastProvider>
            <SidebarProvider>
              <CapabilitiesProvider>
                <div className="flex min-h-screen">
                  <Sidebar />
                  <MainChrome>{children}</MainChrome>
                </div>
                <CommandPalette />
              </CapabilitiesProvider>
            </SidebarProvider>
          </ToastProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
