"use client";
import Link from "next/link";
import {
  ShieldAlert,
  Clock,
  AlertTriangle,
  FileCheck2,
  CheckCircle2,
  ArrowRight,
  Flame,
  Layers,
} from "lucide-react";
import { useOverview } from "@/hooks/items";
import { Empty, ItemRowView } from "@/components/item-row";
import { ErrorState, ListSkeleton } from "@/components/ui";

export default function Overview() {
  const q = useOverview();

  if (q.isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink">Needs attention</h1>
          <p className="mt-1 text-sm text-muted">Checking operational queues and active incidents...</p>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-24 rounded-2xl bg-surface animate-pulse border border-line" />
          ))}
        </div>
        <ListSkeleton rows={4} />
      </div>
    );
  }

  if (q.isError || !q.data) {
    return <ErrorState text="Couldn’t load operational overview." onRetry={() => q.refetch()} />;
  }

  const buckets = q.data.buckets || [];
  const needs = buckets.filter((b) => b.count > 0);

  // Quick stat aggregates
  const approvalBucket = buckets.find((b) => b.key === "awaiting_my_approval");
  const overdueBucket = buckets.find((b) => b.key === "overdue_mine");
  const unownedBucket = buckets.find((b) => b.key === "unowned_urgent");
  const totalNeedingAttention = buckets.reduce((acc, b) => acc + (b.count || 0), 0);

  const getBucketIcon = (key: string) => {
    switch (key) {
      case "awaiting_my_approval":
        return <ShieldAlert className="size-4 text-p1" />;
      case "overdue_mine":
        return <AlertTriangle className="size-4 text-p0" />;
      case "unowned_urgent":
        return <Flame className="size-4 text-p0" />;
      case "blocked_mine":
        return <Clock className="size-4 text-p0" />;
      default:
        return <Layers className="size-4 text-signal" />;
    }
  };

  return (
    <div className="space-y-8 max-w-5xl">
      {/* Page Header */}
      <div>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-ink">
              Mission Overview
            </h1>
            <p className="mt-1 text-sm text-muted">
              {totalNeedingAttention > 0
                ? `${totalNeedingAttention} operational ${
                    totalNeedingAttention === 1 ? "item requires" : "items require"
                  } your attention across teams.`
                : "All operational queues are clear. No pending bottlenecks."}
            </p>
          </div>
          <Link
            href="/items"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-signal hover:underline"
          >
            <span>Browse all work</span>
            <ArrowRight className="size-3.5" />
          </Link>
        </div>

        {/* Quick KPI Stat Cards */}
        <div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
          <Link
            href="/items?view=awaiting_my_approval"
            className="rounded-2xl border border-line bg-surface p-4 shadow-2xs hover:border-signal/40 transition-colors"
          >
            <div className="flex items-center justify-between text-xs text-muted mb-2">
              <span>Approvals</span>
              <ShieldAlert className="size-4 text-p1" />
            </div>
            <p className="text-2xl font-bold text-ink">
              {approvalBucket?.capped ? "999+" : approvalBucket?.count ?? 0}
            </p>
            <span className="text-[11px] text-muted">Waiting on lead sign-off</span>
          </Link>

          <Link
            href="/items?view=unowned_urgent"
            className="rounded-2xl border border-line bg-surface p-4 shadow-2xs hover:border-signal/40 transition-colors"
          >
            <div className="flex items-center justify-between text-xs text-muted mb-2">
              <span>Unowned Urgent</span>
              <Flame className="size-4 text-p0" />
            </div>
            <p className="text-2xl font-bold text-p0">
              {unownedBucket?.capped ? "999+" : unownedBucket?.count ?? 0}
            </p>
            <span className="text-[11px] text-muted">P0 / P1 needs claim</span>
          </Link>

          <Link
            href="/items?view=overdue_mine"
            className="rounded-2xl border border-line bg-surface p-4 shadow-2xs hover:border-signal/40 transition-colors"
          >
            <div className="flex items-center justify-between text-xs text-muted mb-2">
              <span>Overdue</span>
              <AlertTriangle className="size-4 text-p0" />
            </div>
            <p className="text-2xl font-bold text-ink">
              {overdueBucket?.capped ? "999+" : overdueBucket?.count ?? 0}
            </p>
            <span className="text-[11px] text-muted">Past target SLA</span>
          </Link>

          <Link
            href="/items?view=mine"
            className="rounded-2xl border border-line bg-surface p-4 shadow-2xs hover:border-signal/40 transition-colors"
          >
            <div className="flex items-center justify-between text-xs text-muted mb-2">
              <span>Assigned to You</span>
              <CheckCircle2 className="size-4 text-ok" />
            </div>
            <p className="text-2xl font-bold text-ink">
              {buckets.find((b) => b.key === "mine")?.count ??
                buckets.find((b) => b.key === "blocked_mine")?.count ??
                0}
            </p>
            <span className="text-[11px] text-muted">Active items</span>
          </Link>
        </div>
      </div>

      {/* Main Buckets Section */}
      {needs.length === 0 ? (
        <div className="rounded-2xl bg-surface p-12 text-center ring-1 ring-line shadow-sm">
          <div className="mx-auto mb-4 flex size-14 items-center justify-center rounded-full bg-ok/10 text-ok">
            <CheckCircle2 className="size-7" />
          </div>
          <h2 className="text-lg font-bold text-ink">You’re completely clear</h2>
          <p className="mt-1 text-sm text-muted max-w-sm mx-auto">
            No items are waiting on you, overdue, or blocked. Pick up unassigned work or check team backlogs.
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <Link
              href="/items"
              className="rounded-xl bg-ink px-4 py-2.5 text-xs font-semibold text-canvas hover:opacity-90"
            >
              Browse all work
            </Link>
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          {needs.map((b) => (
            <section key={b.key} aria-labelledby={`heading-${b.key}`} className="space-y-2.5">
              <div className="flex items-center justify-between px-1">
                <div className="flex items-center gap-2">
                  <div className="flex size-6 items-center justify-center rounded-md bg-surface border border-line">
                    {getBucketIcon(b.key)}
                  </div>
                  <h2 id={`heading-${b.key}`} className="text-sm font-bold text-ink">
                    {b.label}
                  </h2>
                  <span className="rounded-full bg-canvas px-2 py-0.5 text-xs font-semibold text-muted border border-line">
                    {b.capped ? "999+" : b.count}
                  </span>
                </div>
                <Link
                  href={`/items?view=${b.key}`}
                  className="inline-flex items-center gap-1 text-xs font-medium text-signal hover:underline"
                >
                  <span>See all</span>
                  <ArrowRight className="size-3" />
                </Link>
              </div>

              <div className="divide-y divide-line overflow-hidden rounded-2xl bg-surface ring-1 ring-line shadow-2xs">
                {b.items.map((item) => (
                  <ItemRowView key={item.id ?? item._id ?? item.key} item={item} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
