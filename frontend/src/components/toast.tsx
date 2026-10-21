"use client";
import { createContext, useCallback, useContext, useState } from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import type { ProcessedError } from "@/lib/errors";

type Toast = ProcessedError & { id: number };

type ToastInput =
  | ProcessedError
  | { tone: "error" | "warn" | "info"; text: string; title?: string; actionHint?: string };

const Ctx = createContext<(n: ToastInput) => void>(() => {});

export const useToast = () => useContext(Ctx);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [list, setList] = useState<Toast[]>([]);

  const push = useCallback((input: ToastInput) => {
    const id = Date.now() + Math.random();
    const normalized: ProcessedError = {
      tone: input.tone,
      title: input.title || (input.tone === "error" ? "Error" : input.tone === "warn" ? "Warning" : "Notice"),
      message: (input as any).message || (input as any).text || "An event occurred.",
      text: (input as any).text || (input as any).message || "An event occurred.",
      actionHint: input.actionHint,
      code: (input as any).code || "GENERAL",
      status: (input as any).status || 0,
      requestId: (input as any).requestId,
      meta: (input as any).meta,
    };

    setList((prev) => [...prev.slice(-3), { ...normalized, id }]);
    setTimeout(() => {
      setList((prev) => prev.filter((t) => t.id !== id));
    }, 7000);
  }, []);

  const dismiss = (id: number) => {
    setList((prev) => prev.filter((t) => t.id !== id));
  };

  const getIcon = (tone: "error" | "warn" | "info") => {
    switch (tone) {
      case "error":
        return <AlertCircle className="size-4.5 text-p0 shrink-0 mt-0.5" />;
      case "warn":
        return <AlertTriangle className="size-4.5 text-p1 shrink-0 mt-0.5" />;
      case "info":
        return <Info className="size-4.5 text-signal shrink-0 mt-0.5" />;
      default:
        return <CheckCircle2 className="size-4.5 text-ok shrink-0 mt-0.5" />;
    }
  };

  const getBorderColor = (tone: "error" | "warn" | "info") => {
    switch (tone) {
      case "error":
        return "border-p0/40 bg-surface shadow-p0/10";
      case "warn":
        return "border-p1/40 bg-surface shadow-p1/10";
      case "info":
        return "border-signal/40 bg-surface shadow-signal/10";
      default:
        return "border-line bg-surface";
    }
  };

  return (
    <Ctx.Provider value={push}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-20 z-50 flex flex-col items-center gap-2.5 px-4 md:bottom-6"
      >
        {list.map((t) => (
          <div
            key={t.id}
            role="alert"
            className={`pointer-events-auto flex w-full max-w-md items-start gap-3 rounded-2xl border p-4 shadow-xl backdrop-blur-md transition-all animate-in fade-in-0 slide-in-from-bottom-2 ${getBorderColor(
              t.tone
            )}`}
          >
            {getIcon(t.tone)}

            <div className="flex-1 min-w-0 space-y-1">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-bold text-ink tracking-tight">{t.title}</p>
                {t.code && t.code !== "GENERAL" && (
                  <span className="font-mono text-[9px] uppercase tracking-wider text-muted px-1.5 py-0.2 rounded bg-canvas border border-line">
                    {t.code}
                  </span>
                )}
              </div>

              <p className="text-xs text-ink/90 leading-relaxed">{t.message}</p>

              {t.actionHint && (
                <p className="text-[11px] font-medium text-signal pt-0.5">
                  Hint: {t.actionHint}
                </p>
              )}

              {t.requestId && (
                <p className="text-[10px] font-mono text-muted">Ref: {t.requestId}</p>
              )}
            </div>

            <button
              onClick={() => dismiss(t.id)}
              className="text-muted hover:text-ink transition-colors p-0.5 -mr-1"
            >
              <X className="size-4" />
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
