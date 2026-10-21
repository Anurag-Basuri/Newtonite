"use client";
import { Suspense, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Search,
  Filter,
  X,
  ArrowUpDown,
  RotateCcw,
  Sparkles,
  Layers,
} from "lucide-react";
import { useItems, useTeams } from "@/hooks/items";
import {
  PRIORITY_FILTERS,
  PRIORITY_META,
  SORT_OPTIONS,
  STATUS_FILTERS,
  STATUS_META,
  VIEW_PRESETS,
} from "@/lib/constants";
import { Empty, ItemRowView } from "@/components/item-row";
import { ErrorState, ListSkeleton, btnSecondary } from "@/components/ui";

function List() {
  const sp = useSearchParams();
  const router = useRouter();
  const path = usePathname();

  const currentView = sp.get("view") || "all";
  const currentSort = sp.get("sort") || "-last_activity_at";
  const currentTeam = sp.get("team_id") || "";
  const currentSearch = sp.get("q") || "";

  const [searchInput, setSearchInput] = useState(currentSearch);
  const { data: teams = [] } = useTeams();

  const q = useItems(sp.toString());

  // URL state helpers
  const updateParams = (updater: (params: URLSearchParams) => void) => {
    const next = new URLSearchParams(sp);
    updater(next);
    router.replace(`${path}?${next.toString()}`, { scroll: false });
  };

  const toggle = (k: string, v: string) => {
    updateParams((params) => {
      if (params.has(k, v)) {
        params.delete(k, v);
      } else {
        params.append(k, v);
      }
    });
  };

  const setSingleParam = (k: string, v: string) => {
    updateParams((params) => {
      if (!v || v === "all") {
        params.delete(k);
      } else {
        params.set(k, v);
      }
    });
  };

  const clearAllFilters = () => {
    setSearchInput("");
    router.replace(path, { scroll: false });
  };

  const activeFiltersCount = Array.from(sp.keys()).filter((k) => k !== "sort").length;

  const rows = q.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <div className="space-y-5 max-w-5xl">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-ink">
            All Work
          </h1>
          <p className="mt-1 text-sm text-muted">
            Search, filter, and track work items across authorized operational teams.
          </p>
        </div>

        {/* View Presets Selector */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1 sm:pb-0">
          <select
            value={currentView}
            onChange={(e) => setSingleParam("view", e.target.value)}
            className="rounded-xl border border-line bg-surface px-3 py-2 text-xs font-semibold text-ink shadow-2xs focus:border-signal"
          >
            {VIEW_PRESETS.map((vp) => (
              <option key={vp.key} value={vp.key}>
                {vp.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="rounded-2xl border border-line bg-surface p-4 shadow-2xs space-y-3">
        <div className="flex flex-col sm:flex-row gap-3">
          {/* Quick text filter inside work */}
          <div className="relative flex-1">
            <Search className="absolute left-3 top-2.5 size-4 text-muted" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  setSingleParam("q", searchInput.trim());
                }
              }}
              placeholder="Search in title or key... (press Enter)"
              className="w-full rounded-xl border border-line bg-canvas/50 pl-9 pr-8 py-2 text-xs text-ink placeholder:text-muted focus:border-signal focus:outline-none"
            />
            {searchInput && (
              <button
                onClick={() => {
                  setSearchInput("");
                  setSingleParam("q", "");
                }}
                className="absolute right-2.5 top-2.5 text-muted hover:text-ink"
              >
                <X className="size-3.5" />
              </button>
            )}
          </div>

          {/* Team filter dropdown */}
          {teams.length > 0 && (
            <select
              value={currentTeam}
              onChange={(e) => setSingleParam("team_id", e.target.value)}
              className="rounded-xl border border-line bg-canvas/50 px-3 py-2 text-xs text-ink focus:border-signal"
            >
              <option value="">All teams</option>
              {teams.map((t) => {
                const id = t.team_id || t.team?.id || "";
                const name = t.team_name || t.team?.name || id;
                return (
                  <option key={id} value={id}>
                    {name}
                  </option>
                );
              })}
            </select>
          )}

          {/* Sort selector dropdown */}
          <div className="flex items-center gap-1.5 shrink-0">
            <ArrowUpDown className="size-3.5 text-muted" />
            <select
              value={currentSort}
              onChange={(e) => setSingleParam("sort", e.target.value)}
              className="rounded-xl border border-line bg-canvas/50 px-3 py-2 text-xs text-ink focus:border-signal"
            >
              {SORT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Filter chips for Status and Priority */}
        <div className="flex flex-wrap items-center gap-1.5 pt-2 border-t border-line/60">
          <span className="text-[11px] font-semibold text-muted uppercase tracking-wider mr-1">
            Status:
          </span>
          {STATUS_FILTERS.map((s) => {
            const isPressed = sp.has("status", s);
            return (
              <button
                key={s}
                onClick={() => toggle("status", s)}
                aria-pressed={isPressed}
                className={`min-h-8 rounded-lg border px-2.5 py-1 text-xs font-medium transition-all ${
                  isPressed
                    ? "border-ink bg-ink text-canvas shadow-xs"
                    : "border-line bg-canvas/40 text-muted hover:text-ink hover:bg-canvas"
                }`}
              >
                {STATUS_META[s].label}
              </button>
            );
          })}

          <span className="text-[11px] font-semibold text-muted uppercase tracking-wider ml-2 mr-1">
            Priority:
          </span>
          {PRIORITY_FILTERS.map((p) => {
            const isPressed = sp.has("priority", p);
            return (
              <button
                key={p}
                onClick={() => toggle("priority", p)}
                aria-pressed={isPressed}
                className={`min-h-8 rounded-lg border px-2.5 py-1 text-xs font-semibold transition-all ${
                  isPressed
                    ? "border-ink bg-ink text-canvas shadow-xs"
                    : "border-line bg-canvas/40 text-muted hover:text-ink hover:bg-canvas"
                }`}
              >
                {p}
              </button>
            );
          })}

          {activeFiltersCount > 0 && (
            <button
              onClick={clearAllFilters}
              className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-signal hover:underline py-1"
            >
              <RotateCcw className="size-3" />
              <span>Clear filters ({activeFiltersCount})</span>
            </button>
          )}
        </div>
      </div>

      {/* Results List */}
      {q.isLoading ? (
        <ListSkeleton rows={6} />
      ) : q.isError ? (
        <ErrorState text="Couldn’t load work items." onRetry={() => q.refetch()} />
      ) : (
        <div className="divide-y divide-line overflow-hidden rounded-2xl bg-surface ring-1 ring-line shadow-2xs">
          {rows.length === 0 ? (
            <Empty
              title="No items match your active filters"
              hint="Try clearing filters or switching views to see items in other queues."
              action={
                activeFiltersCount > 0 ? (
                  <button onClick={clearAllFilters} className={btnSecondary}>
                    Clear active filters
                  </button>
                ) : undefined
              }
            />
          ) : (
            rows.map((item) => (
              <ItemRowView key={item.id ?? item._id ?? item.key} item={item} />
            ))
          )}
        </div>
      )}

      {/* Keyset Pagination Load More */}
      {q.hasNextPage && (
        <div className="flex justify-center pt-2">
          <button
            onClick={() => q.fetchNextPage()}
            disabled={q.isFetchingNextPage}
            className={`${btnSecondary} w-full sm:w-auto px-8`}
          >
            {q.isFetchingNextPage ? "Loading more..." : "Load more items"}
          </button>
        </div>
      )}
    </div>
  );
}

export default function Items() {
  return (
    <Suspense
      fallback={
        <div className="space-y-4">
          <div className="h-8 w-48 rounded-xl bg-surface animate-pulse" />
          <ListSkeleton rows={5} />
        </div>
      }
    >
      <List />
    </Suspense>
  );
}
