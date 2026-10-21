import type { ItemType, Priority, Status } from "./types";

/** Single source of truth for how statuses and priorities look and read. */
export const STATUS_META: Record<Status, { label: string; tone: string; dot: string }> = {
  open: { label: "Open", tone: "text-ink border-line bg-surface/80", dot: "bg-muted" },
  triaged: { label: "Triaged", tone: "text-ink border-line bg-surface/80", dot: "bg-line" },
  in_progress: { label: "In progress", tone: "text-signal border-signal/40 bg-signal/10", dot: "bg-signal" },
  blocked: { label: "Blocked", tone: "text-p0 border-p0/40 bg-p0/10", dot: "bg-p0" },
  pending_approval: { label: "Needs approval", tone: "text-p1 border-p1/50 bg-p1/10", dot: "bg-p1" },
  resolved: { label: "Resolved", tone: "text-ok border-ok/40 bg-ok/10", dot: "bg-ok" },
  closed: { label: "Closed", tone: "text-muted border-line bg-surface/50", dot: "bg-muted" },
};

export const PRIORITY_META: Record<Priority, { label: string; shortLabel: string; bar: string; badge: string; glow: string }> = {
  P0: { label: "P0 · Critical", shortLabel: "Critical", bar: "bg-p0", badge: "text-p0 border-p0/40 bg-p0/10", glow: "shadow-[0_0_12px_rgba(196,34,45,0.35)]" },
  P1: { label: "P1 · High", shortLabel: "High", bar: "bg-p1", badge: "text-p1 border-p1/40 bg-p1/10", glow: "shadow-[0_0_12px_rgba(184,110,0,0.25)]" },
  P2: { label: "P2 · Normal", shortLabel: "Normal", bar: "bg-p2", badge: "text-p2 border-p2/40 bg-p2/10", glow: "" },
  P3: { label: "P3 · Low", shortLabel: "Low", bar: "bg-p3", badge: "text-p3 border-p3/40 bg-p3/10", glow: "" },
};

export const ITEM_TYPE_META: Record<string, { label: string; color: string; dot: string; tone: string }> = {
  customer_issue: {
    label: "Customer Issue",
    color: "text-p2",
    dot: "bg-p2",
    tone: "text-p2 border-p2/30 bg-p2/10",
  },
  engineering: {
    label: "Engineering Problem",
    color: "text-signal",
    dot: "bg-signal",
    tone: "text-signal border-signal/30 bg-signal/10",
  },
  payment: {
    label: "Payment Exception",
    color: "text-p1",
    dot: "bg-p1",
    tone: "text-p1 border-p1/30 bg-p1/10",
  },
  incident: {
    label: "Production Incident",
    color: "text-p0",
    dot: "bg-p0",
    tone: "text-p0 border-p0/30 bg-p0/10",
  },
  compliance: {
    label: "Compliance Request",
    color: "text-ok",
    dot: "bg-ok",
    tone: "text-ok border-ok/30 bg-ok/10",
  },
  task: {
    label: "Operational Task",
    color: "text-muted",
    dot: "bg-muted",
    tone: "text-muted border-line bg-surface/80",
  },
  // Backwards compatibility aliases
  system_alert: {
    label: "Production Incident",
    color: "text-p0",
    dot: "bg-p0",
    tone: "text-p0 border-p0/30 bg-p0/10",
  },
  access_request: {
    label: "Access Request",
    color: "text-ink",
    dot: "bg-muted",
    tone: "text-ink border-line bg-surface/80",
  },
};

export const STATUS_FILTERS = ["open", "triaged", "in_progress", "blocked", "pending_approval", "resolved", "closed"] as const;
export const PRIORITY_FILTERS = ["P0", "P1", "P2", "P3"] as const;
export const ITEM_TYPE_FILTERS = ["customer_issue", "engineering", "payment", "incident", "compliance", "task"] as const;

export const VIEW_PRESETS = [
  { key: "all", label: "All items" },
  { key: "mine", label: "Assigned to me" },
  { key: "unowned_urgent", label: "Unowned urgent" },
  { key: "awaiting_my_approval", label: "Needs approval" },
  { key: "overdue_mine", label: "Overdue" },
  { key: "blocked_mine", label: "Blocked" },
  { key: "stale", label: "Stale" },
  { key: "created_by_me", label: "Created by me" },
] as const;

export const SORT_OPTIONS = [
  { value: "-last_activity_at", label: "Recently active" },
  { value: "priority", label: "Highest priority (P0 first)" },
  { value: "due_at", label: "Due date (earliest first)" },
  { value: "-created_at", label: "Newest created" },
] as const;
