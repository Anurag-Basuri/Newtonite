"use client";
import { createContext, useCallback, useContext, useState } from "react";
import type { Notice } from "@/lib/errors";
type Toast = Notice & { id: number };
const Ctx = createContext<(n: Notice) => void>(() => {});
export const useToast = () => useContext(Ctx);
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [list, setList] = useState<Toast[]>([]);
  const push = useCallback((n: Notice) => {
    const id = Date.now() + Math.random();
    setList((l) => [...l.slice(-2), { ...n, id }]);
    setTimeout(() => setList((l) => l.filter((t) => t.id !== id)), 6000);
  }, []);
  return (
    <Ctx.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-20 z-50 flex flex-col items-center gap-2 px-4 md:bottom-6">
        {list.map((t) => (
          <p key={t.id} className={`pointer-events-auto w-full max-w-sm rounded-lg border bg-surface px-4 py-3 text-sm shadow-lg ${t.tone === "error" ? "border-p0/50" : "border-p1/50"}`}>{t.text}</p>
        ))}
      </div>
    </Ctx.Provider>
  );
}
