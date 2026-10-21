import type { Priority, Status } from "@/lib/types";
import { ITEM_TYPE_META, PRIORITY_META, STATUS_META } from "@/lib/constants";
export { shortDate, timeAgo } from "@/lib/format";

export const PRIORITY_COLOR = (p: Priority) => PRIORITY_META[p]?.bar ?? "bg-p2";

export const StatusBadge = ({ status }: { status: Status }) => {
  const meta = STATUS_META[status] ?? { label: status, tone: "text-muted border-line bg-surface", dot: "bg-muted" };
  return (
    <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${meta.tone}`}>
      <span className={`size-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  );
};

export const PriorityMark = ({ p }: { p: Priority }) => {
  const meta = PRIORITY_META[p] ?? PRIORITY_META.P2;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-semibold ${meta.badge}`}>
      <span aria-hidden className={`size-2 rounded-full ${meta.bar} ${p === "P0" ? "animate-ping opacity-75" : ""}`} />
      {meta.label}
    </span>
  );
};

export const TypeBadge = ({ type }: { type: string }) => {
  const meta = ITEM_TYPE_META[type] ?? { label: type.replace(/_/g, " "), color: "text-muted" };
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted font-normal">
      <span className="size-1 rounded-full bg-muted/60" />
      {meta.label}
    </span>
  );
};
