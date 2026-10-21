"use client";
import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { Search, Plus, List, LayoutDashboard, Clock, AlertTriangle, ArrowRight, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { StatusBadge } from "./badges";
import type { Status } from "@/lib/types";

type AutocompleteItem = {
  key: string;
  title: string;
  status: Status;
  priority?: string;
};

export function CommandPalette({
  open,
  onClose,
  onOpenCreate,
}: {
  open: boolean;
  onClose: () => void;
  onOpenCreate: () => void;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<AutocompleteItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
      setQuery("");
      setResults([]);
      setSelectedIndex(0);
    }
  }, [open]);

  // Debounced search
  useEffect(() => {
    if (!query.trim() || query.length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await api<{ items: AutocompleteItem[] }>(
          `/search?q=${encodeURIComponent(query.trim())}&mode=autocomplete&limit=8`
        );
        setResults(res.items || []);
        setSelectedIndex(0);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 200);
    return () => clearTimeout(t);
  }, [query]);

  // Keyboard navigation inside palette
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (results.length > 0 ? (prev + 1) % results.length : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => (results.length > 0 ? (prev - 1 + results.length) % results.length : 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (results[selectedIndex]) {
        router.push(`/items/${results[selectedIndex].key}`);
        onClose();
      } else if (query.trim()) {
        router.push(`/items?q=${encodeURIComponent(query.trim())}`);
        onClose();
      }
    }
  };

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4 sm:pt-28"
    >
      <div
        className="fixed inset-0 bg-black/45 backdrop-blur-xs transition-opacity"
        onClick={onClose}
      />
      <div className="relative z-10 w-full max-w-xl overflow-hidden rounded-2xl bg-surface shadow-2xl ring-1 ring-line animate-in fade-in-0 zoom-in-95 duration-100">
        {/* Search Input Bar */}
        <div className="flex items-center border-b border-line px-4 py-3">
          <Search className="size-5 text-muted shrink-0 mr-3" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search items by key, title, or keyword... (e.g. PAY-143, refund)"
            className="w-full bg-transparent text-sm text-ink placeholder:text-muted focus:outline-none"
          />
          {loading && <Loader2 className="size-4 animate-spin text-muted shrink-0 ml-2" />}
          <kbd className="hidden sm:inline-flex items-center rounded border border-line bg-canvas px-1.5 py-0.5 text-[10px] font-mono text-muted ml-2">
            ESC
          </kbd>
        </div>

        {/* Results / Navigation shortcuts */}
        <div className="max-h-80 overflow-y-auto p-2">
          {query.trim().length >= 2 ? (
            results.length > 0 ? (
              <div className="space-y-1">
                <p className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
                  Matching items
                </p>
                {results.map((item, idx) => (
                  <button
                    key={item.key}
                    onClick={() => {
                      router.push(`/items/${item.key}`);
                      onClose();
                    }}
                    onMouseEnter={() => setSelectedIndex(idx)}
                    className={`flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left text-sm transition-colors ${
                      selectedIndex === idx ? "bg-canvas text-ink" : "text-muted hover:text-ink"
                    }`}
                  >
                    <div className="flex min-w-0 items-center gap-2.5">
                      <span className="font-mono text-xs font-semibold text-signal shrink-0">
                        {item.key}
                      </span>
                      <span className="truncate font-medium text-ink">{item.title}</span>
                    </div>
                    <StatusBadge status={item.status} />
                  </button>
                ))}
              </div>
            ) : !loading ? (
              <div className="px-4 py-8 text-center">
                <p className="text-sm font-medium text-ink">No items found matching "{query}"</p>
                <p className="mt-1 text-xs text-muted">Press Enter to search all items or try different words.</p>
              </div>
            ) : null
          ) : (
            <div className="space-y-1">
              <p className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
                Quick Actions
              </p>
              <button
                onClick={() => {
                  onClose();
                  onOpenCreate();
                }}
                className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-ink hover:bg-canvas transition-colors"
              >
                <div className="flex size-7 items-center justify-center rounded-md bg-signal/10 text-signal">
                  <Plus className="size-4" />
                </div>
                <div className="flex-1">
                  <p className="font-medium">Create new operational item</p>
                  <p className="text-xs text-muted">File an issue, ticket, or exception</p>
                </div>
                <ArrowRight className="size-4 text-muted" />
              </button>

              <button
                onClick={() => {
                  router.push("/items?view=mine");
                  onClose();
                }}
                className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-ink hover:bg-canvas transition-colors"
              >
                <div className="flex size-7 items-center justify-center rounded-md bg-line/60 text-muted">
                  <Clock className="size-4" />
                </div>
                <div className="flex-1">
                  <p className="font-medium">My assigned work</p>
                  <p className="text-xs text-muted">View work currently assigned to you</p>
                </div>
                <ArrowRight className="size-4 text-muted" />
              </button>

              <button
                onClick={() => {
                  router.push("/items?view=unowned_urgent");
                  onClose();
                }}
                className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-ink hover:bg-canvas transition-colors"
              >
                <div className="flex size-7 items-center justify-center rounded-md bg-p0/10 text-p0">
                  <AlertTriangle className="size-4" />
                </div>
                <div className="flex-1">
                  <p className="font-medium">Unowned urgent (P0 / P1)</p>
                  <p className="text-xs text-muted">Items waiting to be claimed</p>
                </div>
                <ArrowRight className="size-4 text-muted" />
              </button>

              <button
                onClick={() => {
                  router.push("/overview");
                  onClose();
                }}
                className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-ink hover:bg-canvas transition-colors"
              >
                <div className="flex size-7 items-center justify-center rounded-md bg-line/60 text-muted">
                  <LayoutDashboard className="size-4" />
                </div>
                <div className="flex-1">
                  <p className="font-medium">Overview dashboard</p>
                  <p className="text-xs text-muted">Critical attention buckets</p>
                </div>
                <ArrowRight className="size-4 text-muted" />
              </button>
            </div>
          )}
        </div>

        {/* Footer shortcuts info */}
        <div className="flex items-center justify-between border-t border-line bg-canvas/40 px-4 py-2 text-[11px] text-muted">
          <span>Navigate with <kbd className="rounded border border-line bg-surface px-1 py-0.5">↑</kbd> <kbd className="rounded border border-line bg-surface px-1 py-0.5">↓</kbd></span>
          <span>Open with <kbd className="rounded border border-line bg-surface px-1 py-0.5">↵</kbd></span>
        </div>
      </div>
    </div>
  );
}
