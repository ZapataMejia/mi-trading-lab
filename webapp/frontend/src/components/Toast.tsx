"use client";

import { createContext, useCallback, useContext, useState } from "react";
import { CheckCircle, AlertCircle, Info, X } from "lucide-react";

type ToastVariant = "success" | "error" | "info";
interface Toast {
  id: number;
  message: string;
  variant: ToastVariant;
}

const ToastCtx = createContext<{
  push: (msg: string, variant?: ToastVariant) => void;
} | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const push = useCallback((message: string, variant: ToastVariant = "info") => {
    setToasts((cur) => {
      const dup = cur.some((t) => t.message === message && t.variant === variant);
      if (dup) return cur;
      const id = Date.now() + Math.random();
      setTimeout(() => setToasts((c) => c.filter((t) => t.id !== id)), 5000);
      return [...cur, { id, message, variant }];
    });
  }, []);

  return (
    <ToastCtx.Provider value={{ push }}>
      {children}
      <div className="fixed bottom-4 right-4 flex flex-col gap-2 z-50 max-w-md">
        {toasts.map((t) => (
          <ToastItem
            key={t.id}
            toast={t}
            onClose={() => setToasts((cur) => cur.filter((x) => x.id !== t.id))}
          />
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast must be inside ToastProvider");
  return ctx;
}

function ToastItem({ toast, onClose }: { toast: Toast; onClose: () => void }) {
  const colors = {
    success: { bg: "var(--green-light)", border: "var(--green)", icon: "var(--green)" },
    error: { bg: "var(--red-light)", border: "var(--red)", icon: "var(--red)" },
    info: { bg: "var(--bg-card)", border: "var(--border-strong)", icon: "var(--text-muted)" },
  }[toast.variant];

  const Icon = { success: CheckCircle, error: AlertCircle, info: Info }[toast.variant];

  return (
    <div
      className="toast flex items-start gap-2 p-3 rounded-lg border min-w-[280px] shadow-lg"
      style={{ background: colors.bg, borderColor: colors.border }}
    >
      <Icon size={16} strokeWidth={1.75} style={{ color: colors.icon, marginTop: 2 }} />
      <div className="flex-1 text-sm" style={{ color: "var(--text)" }}>
        {toast.message}
      </div>
      <button onClick={onClose} className="btn-ghost" style={{ padding: "2px 4px" }}>
        <X size={14} strokeWidth={1.75} />
      </button>
    </div>
  );
}
