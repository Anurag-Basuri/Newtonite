import Link from "next/link";
import type { ItemRow } from "@/lib/types";
import { PRIORITY_COLOR, StatusBadge, TypeBadge, timeAgo } from "./badges";
import { Clock, AlertTriangle, ShieldAlert } from "lucide-react";

/** Left rail = priority (always visible). Hatched rail = overdue or going stale. Stacks on phones, one line on desktop. */
export function ItemRowView({ item }: { item: ItemRow }) {
  const isOverdue =
    item.attention?.includes("overdue") ||
    (item.due_at && new Date(item.due_at).getTime() < Date.now() && item.status !== "resolved" && item.status !== "closed");

  const isStale =
    item.attention?.includes("stale") ||
    (item.attention_due_at && new Date(item.attention_due_at).getTime() < Date.now() && item.status !== "resolved" && item.status !== "closed");

  const flagged = isOverdue || isStale;
  const isP0 = item.priority === "P0";

  const teamName = item.team?.name || item.team_id || "Team";
  const assigneeName = item.assignee?.name || (item.assignee_id ? "Assigned" : "Unassigned");
  const activityTime = item.last_activity_at || item.updated_at || item.created_at || new Date().toISOString();

  return (
    <Link
      href={`/items/${item.key}`}
      className="group relative flex items-stretch bg-surface transition-all duration-150 hover:bg-canvas/50 focus-visible:-outline-offset-2"
    >
      {/* Priority accent stripe */}
      <span
        aria-hidden
        className={`w-1.5 shrink-0 transition-all ${PRIORITY_COLOR(item.priority)} ${
          isP0 ? "shadow-[0_0_8px_rgba(196,34,45,0.6)]" : ""
        } ${
          flagged
            ? "[background-image:repeating-linear-gradient(135deg,transparent_0_4px,rgba(255,255,255,.45)_4px_6px)]"
            : ""
        }`}
      />

      <div className="flex min-w-0 flex-1 flex-col gap-1.5 px-4 py-3 sm:flex-row sm:items-center sm:gap-4">
        {/* Key and status on mobile / desktop */}
        <div className="flex items-center justify-between gap-2 sm:contents">
          <span className="font-mono text-xs font-semibold tracking-tight text-muted group-hover:text-signal transition-colors sm:w-20 sm:shrink-0">
            {item.key}
          </span>
          <span className="sm:order-last shrink-0">
            <StatusBadge status={item.status} />
          </span>
        </div>

        {/* Title and metadata */}
        <div className="min-w-0 flex-1 space-y-0.5">
          <div className="flex items-center gap-2">
            <p className="line-clamp-2 text-sm font-medium text-ink group-hover:text-signal transition-colors sm:truncate">
              {item.title}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted">
            <span>{teamName}</span>
            <span>·</span>
            <TypeBadge type={item.type} />
            <span>·</span>
            <span className={item.assignee ? "text-ink font-normal" : "text-muted italic"}>
              {assigneeName}
            </span>
            <span>·</span>
            <span title={activityTime}>{timeAgo(activityTime)}</span>
          </div>
        </div>

        {/* Attention warnings */}
        <div className="flex items-center gap-2 shrink-0">
          {isOverdue && (
            <span className="inline-flex items-center gap-1 rounded-md border border-p0/30 bg-p0/10 px-2 py-0.5 text-xs font-semibold text-p0">
              <AlertTriangle className="size-3" />
              Overdue
            </span>
          )}
          {isStale && !isOverdue && (
            <span className="inline-flex items-center gap-1 rounded-md border border-p1/30 bg-p1/10 px-2 py-0.5 text-xs font-medium text-p1">
              <Clock className="size-3" />
              Stale
            </span>
          )}
          {item.status === "pending_approval" && (
            <span className="inline-flex items-center gap-1 rounded-md border border-p1/40 bg-p1/10 px-2 py-0.5 text-xs font-medium text-p1">
              <ShieldAlert className="size-3" />
              Approval pending
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}

export const Empty = ({ title, hint, action }: { title: string; hint?: string; action?: React.ReactNode }) => (
  <div className="flex flex-col items-center justify-center px-4 py-12 text-center">
    <div className="mb-3 flex size-12 items-center justify-center rounded-full bg-line/40 text-muted">
      <Clock className="size-6 stroke-[1.5]" />
    </div>
    <p className="text-sm font-semibold text-ink">{title}</p>
    {hint && <p className="mt-1 max-w-sm text-xs text-muted leading-relaxed">{hint}</p>}
    {action && <div className="mt-4">{action}</div>}
  </div>
);
