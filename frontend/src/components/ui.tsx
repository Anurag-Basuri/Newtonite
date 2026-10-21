import React from "react";
import { Loader2 } from "lucide-react";

export const Skeleton = ({ className = "" }: { className?: string }) => (
  <div aria-hidden className={`animate-pulse rounded-md bg-line/70 ${className}`} />
);

export const ListSkeleton = ({ rows = 5 }: { rows?: number }) => (
  <div
    className="divide-y divide-line overflow-hidden rounded-xl bg-surface ring-1 ring-line"
    role="status"
    aria-label="Loading"
  >
    {Array.from({ length: rows }, (_, i) => (
      <div key={i} className="space-y-2 px-4 py-4">
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-3 w-1/3" />
      </div>
    ))}
  </div>
);

export const ErrorState = ({ text, onRetry }: { text: string; onRetry?: () => void }) => (
  <div role="alert" className="rounded-xl bg-surface px-4 py-8 text-center ring-1 ring-line">
    <p className="text-sm text-ink">{text}</p>
    {onRetry && (
      <button
        onClick={onRetry}
        className="mt-3 min-h-11 rounded-md border border-line px-4 text-sm font-medium text-ink transition-colors hover:bg-canvas md:min-h-9"
      >
        Try again
      </button>
    )}
  </div>
);

export const Spinner = ({ className = "size-4" }: { className?: string }) => (
  <Loader2 className={`animate-spin ${className}`} />
);

export const btn =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium transition-all duration-150 disabled:pointer-events-none disabled:opacity-50 md:min-h-9 cursor-pointer select-none";

export const btnPrimary = `${btn} bg-ink text-canvas hover:opacity-90 active:scale-[0.98] shadow-sm`;
export const btnSignal = `${btn} bg-signal text-white hover:bg-signal-hover active:scale-[0.98] shadow-sm`;
export const btnSecondary = `${btn} border border-line bg-surface text-ink hover:bg-canvas active:scale-[0.98] shadow-sm`;
export const btnDanger = `${btn} border border-p0/40 bg-p0/10 text-p0 hover:bg-p0/20 active:scale-[0.98]`;
export const btnSuccess = `${btn} border border-ok/40 bg-ok/10 text-ok hover:bg-ok/20 active:scale-[0.98]`;
export const btnGhost = `${btn} text-muted hover:text-ink hover:bg-canvas active:scale-[0.98]`;

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  maxWidth = "max-w-lg",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  maxWidth?: string;
}) {
  if (!open) return null;
  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
    >
      <div
        className="fixed inset-0 bg-black/40 backdrop-blur-xs transition-opacity"
        onClick={onClose}
      />
      <div
        className={`relative z-10 w-full ${maxWidth} rounded-2xl bg-surface p-6 shadow-2xl ring-1 ring-line overflow-hidden max-h-[90vh] flex flex-col`}
      >
        <div className="mb-4">
          <h2 className="text-lg font-semibold tracking-tight text-ink">{title}</h2>
          {description && <p className="mt-1 text-xs text-muted leading-relaxed">{description}</p>}
        </div>
        <div className="overflow-y-auto min-h-0 flex-1">{children}</div>
      </div>
    </div>
  );
}
