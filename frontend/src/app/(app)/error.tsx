"use client";
import Link from "next/link";
import { AlertTriangle, ServerOff, RotateCw, ArrowLeft } from "lucide-react";
import { explain } from "@/lib/errors";
import { btnPrimary, btnSecondary } from "@/components/ui";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const p = explain(error);
  const isOffline = p.code === "SERVER_OFFLINE" || p.status === 0;

  return (
    <div className="flex min-h-[60vh] items-center justify-center p-4">
      <div className="w-full max-w-md rounded-2xl border border-line bg-surface p-8 shadow-xl text-center space-y-4">
        <div
          className={`mx-auto flex size-12 items-center justify-center rounded-2xl ${
            isOffline ? "bg-p0/10 text-p0" : "bg-p1/10 text-p1"
          }`}
        >
          {isOffline ? <ServerOff className="size-6" /> : <AlertTriangle className="size-6" />}
        </div>

        <div>
          <h2 className="text-lg font-bold text-ink">{p.title}</h2>
          <p className="mt-1.5 text-xs text-muted leading-relaxed">{p.message}</p>
          {p.actionHint && (
            <p className="mt-2 text-xs font-medium text-signal">Tip: {p.actionHint}</p>
          )}
        </div>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-2 pt-2">
          <button onClick={reset} className={`${btnPrimary} w-full sm:w-auto`}>
            <RotateCw className="size-3.5" />
            <span>Try again</span>
          </button>
          <Link href="/overview" className={`${btnSecondary} w-full sm:w-auto`}>
            <ArrowLeft className="size-3.5" />
            <span>Go to Overview</span>
          </Link>
        </div>
      </div>
    </div>
  );
}
