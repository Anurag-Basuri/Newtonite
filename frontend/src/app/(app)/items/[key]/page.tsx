"use client";
import { use, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle2,
  Clock,
  AlertTriangle,
  ShieldAlert,
  Send,
  UserCheck,
  UserX,
  Sparkles,
  MessageSquare,
  History,
  Tag,
  Calendar,
  User,
  Shield,
  ExternalLink,
  ChevronRight,
  Flame,
} from "lucide-react";
import { ApiError, newKey } from "@/lib/api";
import { explain, isVersionConflict } from "@/lib/errors";
import { shortDate, timeAgo } from "@/lib/format";
import { STATUS_META, PRIORITY_META } from "@/lib/constants";
import {
  useAssign,
  useClaim,
  useComment,
  useDecideApproval,
  useItem,
  useItemSimilar,
  useMe,
  usePatchItem,
  useRelease,
  useRequestApproval,
  useTeamMembers,
  useTimeline,
  useTransition,
} from "@/hooks/items";
import { PriorityMark, StatusBadge, TypeBadge } from "@/components/badges";
import { useToast } from "@/components/toast";
import { ListSkeleton, Modal, btnDanger, btnPrimary, btnSecondary, btnSuccess } from "@/components/ui";
import { AiAssistantWidget } from "@/components/ai-assistant-drawer";
import type { Status, TimelineEvent } from "@/lib/types";

const describeEvent = (e: TimelineEvent) => {
  const p = e.payload || {};
  switch (e.type) {
    case "comment.added":
      return p.body as string;
    case "item.status_changed":
      return `Moved status from ${p.from} to ${p.to}${p.reason ? ` · Reason: ${p.reason}` : ""}`;
    case "item.priority_changed":
      return `Priority changed from ${p.from} to ${p.to}`;
    case "item.claimed":
      return "Claimed ownership of this item";
    case "item.released":
      return "Released ownership back to the queue";
    case "item.assigned":
      return `Assigned item to ${p.assignee_name || p.assignee_id || "team member"}`;
    case "approval.requested":
      return `Requested approval: ${p.request_note || "Ready for review"}`;
    case "approval.decided":
      return `${p.approved ? "Approved" : "Rejected"} by lead: ${p.decision_reason || ""}`;
    case "item.created":
      return "Created work item";
    default:
      return e.type.replace(/[._]/g, " ");
  }
};

export default function ItemPage({ params }: { params: Promise<{ key: string }> }) {
  const { key } = use(params);
  const toast = useToast();
  const me = useMe();
  const item = useItem(key);
  const tl = useTimeline(key);
  const similarItemsQuery = useItemSimilar(key);

  const claim = useClaim(key, me.data);
  const release = useRelease(key);
  const assign = useAssign(key);
  const move = useTransition(key);
  const comment = useComment(key);
  const patch = usePatchItem(key);
  const requestApproval = useRequestApproval(key);

  const [conflict, setConflict] = useState<ApiError | null>(null);
  const [commentText, setCommentText] = useState("");

  // Modals state
  const [transitionModal, setTransitionModal] = useState<{ open: boolean; to: Status | "" }>({
    open: false,
    to: "",
  });
  const [transitionReason, setTransitionReason] = useState("");
  const [transitionResolution, setTransitionResolution] = useState<string>("completed");
  const [transitionDuplicateOf, setTransitionDuplicateOf] = useState("");
  const [approvalModalOpen, setApprovalModalOpen] = useState(false);
  const [approvalNote, setApprovalNote] = useState("");
  const [decisionModal, setDecisionModal] = useState<{ open: boolean; approved: boolean }>({
    open: false,
    approved: true,
  });
  const [decisionReason, setDecisionReason] = useState("");
  const [assignModalOpen, setAssignModalOpen] = useState(false);
  const [selectedAssignee, setSelectedAssignee] = useState("");

  const onError = (e: Error) => (isVersionConflict(e) ? setConflict(e) : toast(explain(e)));
  const onOk = () => setConflict(null);

  if (item.isLoading) {
    return (
      <div className="space-y-6 max-w-5xl">
        <div className="h-8 w-32 rounded-xl bg-surface animate-pulse" />
        <div className="h-48 rounded-2xl bg-surface animate-pulse" />
        <ListSkeleton rows={3} />
      </div>
    );
  }

  if (item.isError || !item.data) {
    const p = explain(item.error);
    return (
      <div className="rounded-2xl bg-surface p-10 text-center ring-1 ring-line max-w-lg mx-auto shadow-sm space-y-3">
        <AlertTriangle className="size-10 text-p1 mx-auto" />
        <h2 className="text-lg font-bold text-ink">{p.title}</h2>
        <p className="text-xs text-muted leading-relaxed max-w-sm mx-auto">
          {p.message}
        </p>
        {p.actionHint && (
          <p className="text-xs font-medium text-signal">Tip: {p.actionHint}</p>
        )}
        <div className="pt-3 flex items-center justify-center gap-3">
          <button onClick={() => item.refetch()} className={btnSecondary}>
            Try reloading
          </button>
          <Link href="/items" className={btnPrimary}>
            Back to all work
          </Link>
        </div>
      </div>
    );
  }

  const it = item.data;
  const p = it.permissions;
  const busy =
    claim.isPending ||
    release.isPending ||
    assign.isPending ||
    move.isPending ||
    patch.isPending ||
    requestApproval.isPending;

  // Check roles
  const teamId = it.team?.id || it.team_id || "";
  const userTeamMembership = me.data?.teams.find((t) => t.team_id === teamId || t.team?.id === teamId);
  const isLead = me.data?.is_org_admin || userTeamMembership?.role === "lead";
  const isAssignedToMe = Boolean(me.data?.user.id && (it.assignee?.id === me.data.user.id || it.assignee_id === me.data.user.id));

  // Timeline events normalized
  const timelineEvents = tl.data?.items ?? [];

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Top back breadcrumb & Quick actions */}
      <div className="flex items-center justify-between">
        <Link
          href="/items"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted hover:text-ink transition-colors"
        >
          <ArrowLeft className="size-3.5" />
          <span>All work</span>
        </Link>
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs font-bold text-muted px-2 py-0.5 rounded-md bg-canvas border border-line">
            v{it.version}
          </span>
        </div>
      </div>

      {/* Main Grid: Left workbench, Right details & assistant */}
      <div className="grid gap-8 lg:grid-cols-[1fr_20rem]">
        <div className="min-w-0 space-y-6">
          {/* Header Card */}
          <div className="rounded-2xl border border-line bg-surface p-6 shadow-sm space-y-4">
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="font-mono text-xs font-bold text-signal bg-signal/10 px-2.5 py-1 rounded-lg">
                {it.key}
              </span>
              <StatusBadge status={it.status} />
              <PriorityMark p={it.priority} />
              <TypeBadge type={it.type} />
              {it.resolution && (
                <span className="inline-flex items-center gap-1 rounded-lg border border-line bg-canvas px-2.5 py-0.5 text-xs font-medium text-muted capitalize">
                  Resolution: {it.resolution.replace("_", " ")}
                  {it.duplicate_of && ` (${it.duplicate_of})`}
                </span>
              )}
            </div>

            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-ink leading-tight">
              {it.title}
            </h1>

            {/* Version Conflict Warning Banner */}
            {conflict && (
              <ConflictPanel
                err={conflict}
                onReload={() => {
                  setConflict(null);
                  item.refetch();
                  tl.refetch();
                }}
              />
            )}

            {/* Approval Decision Banner (for Leads when item is in pending_approval) */}
            {it.status === "pending_approval" && (
              <div className="rounded-xl border border-p1/40 bg-p1/10 p-4 space-y-2">
                <div className="flex items-center gap-2 font-bold text-p1 text-sm">
                  <ShieldAlert className="size-4.5" />
                  <span>Pending Lead Approval</span>
                </div>
                <p className="text-xs text-ink/90 leading-relaxed">
                  This operational item requires peer lead sign-off before being resolved.
                  {me.data?.user.id === it.reporter?.id && (
                    <span className="block mt-1 text-p0 font-medium">
                      Four-eyes policy: You cannot approve your own request.
                    </span>
                  )}
                </p>
                {isLead && me.data?.user.id !== it.reporter?.id && (
                  <div className="flex items-center gap-2 pt-2">
                    <button
                      onClick={() => setDecisionModal({ open: true, approved: true })}
                      className={btnSuccess}
                    >
                      <CheckCircle2 className="size-4" />
                      Approve request
                    </button>
                    <button
                      onClick={() => setDecisionModal({ open: true, approved: false })}
                      className={btnDanger}
                    >
                      Reject with reason
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Action Bar */}
            <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-line/60">
              {/* Claim ownership */}
              {p.can_claim && (
                <button
                  disabled={busy}
                  onClick={() => claim.mutate(newKey(), { onError, onSuccess: onOk })}
                  className={btnPrimary}
                >
                  <UserCheck className="size-4" />
                  <span>Take ownership</span>
                </button>
              )}

              {/* Release ownership */}
              {(isAssignedToMe || (isLead && it.assignee_id)) && (
                <button
                  disabled={busy}
                  onClick={() => release.mutate(undefined, { onError, onSuccess: onOk })}
                  className={btnSecondary}
                >
                  <UserX className="size-4" />
                  <span>Release ownership</span>
                </button>
              )}

              {/* Request Approval button */}
              {it.requires_approval && it.status === "in_progress" && (
                <button
                  disabled={busy}
                  onClick={() => setApprovalModalOpen(true)}
                  className={btnSecondary}
                >
                  <ShieldAlert className="size-4 text-p1" />
                  <span>Request lead approval</span>
                </button>
              )}

              {/* State Transitions */}
              {p.allowed_transitions.map((to) => (
                <button
                  key={to}
                  disabled={busy}
                  onClick={() => {
                    if (to === "blocked" || to === "closed" || to === "resolved") {
                      setTransitionModal({ open: true, to });
                      setTransitionReason("");
                      setTransitionResolution(to === "closed" ? "cancelled" : "completed");
                      setTransitionDuplicateOf("");
                    } else {
                      move.mutate(
                        { to, version: it.version },
                        { onError, onSuccess: onOk }
                      );
                    }
                  }}
                  className={btnSecondary}
                >
                  <span>Move to {STATUS_META[to]?.label.toLowerCase()}</span>
                </button>
              ))}

              {/* Escalate to P0 */}
              {p.can_edit && it.priority !== "P0" && isLead && (
                <button
                  disabled={busy}
                  onClick={() =>
                    patch.mutate(
                      { patch: { priority: "P0" }, version: it.version },
                      { onError, onSuccess: onOk }
                    )
                  }
                  className={btnSecondary}
                >
                  <Flame className="size-4 text-p0" />
                  <span>Escalate to P0</span>
                </button>
              )}
            </div>

            {/* Description */}
            {it.description ? (
              <div className="pt-2 text-sm text-ink leading-relaxed whitespace-pre-wrap border-t border-line/60">
                {it.description}
              </div>
            ) : (
              <p className="text-xs italic text-muted pt-2 border-t border-line/60">
                No description provided.
              </p>
            )}
          </div>

          {/* Audit Timeline & History */}
          <section
            aria-labelledby="history-heading"
            className="rounded-2xl border border-line bg-surface p-6 shadow-sm space-y-4"
          >
            <div className="flex items-center gap-2">
              <History className="size-4.5 text-muted" />
              <h2 id="history-heading" className="text-base font-bold text-ink">
                Audit Timeline ({timelineEvents.length})
              </h2>
            </div>

            {timelineEvents.length === 0 ? (
              <p className="text-xs text-muted py-4">No recorded history yet.</p>
            ) : (
              <ol className="relative border-l border-line ml-3 space-y-5 py-2">
                {timelineEvents.map((e) => (
                  <li key={e.id} id={`event-${e.seq}`} className="ml-5 scroll-mt-24">
                    <span className="absolute -left-1.5 mt-1.5 size-3 rounded-full border-2 border-surface bg-signal" />
                    <div className="flex items-baseline gap-2 text-xs text-muted">
                      <span className="font-semibold text-ink">{e.actor?.name || "System"}</span>
                      <span>·</span>
                      <time dateTime={e.at} title={shortDate(e.at)}>
                        {timeAgo(e.at)}
                      </time>
                      <span className="text-[10px] text-muted">#{e.seq}</span>
                    </div>
                    <p className="mt-1 text-sm text-ink/90 whitespace-pre-wrap break-words leading-relaxed">
                      {describeEvent(e)}
                    </p>
                  </li>
                ))}
              </ol>
            )}

            {/* Add Comment Box */}
            {p.can_comment && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (commentText.trim()) {
                    comment.mutate(commentText.trim(), {
                      onError,
                      onSuccess: () => setCommentText(""),
                    });
                  }
                }}
                className="space-y-2 pt-4 border-t border-line"
              >
                <label htmlFor="comment-box" className="block text-xs font-semibold text-muted uppercase tracking-wider">
                  Post a comment
                </label>
                <textarea
                  id="comment-box"
                  rows={3}
                  value={commentText}
                  onChange={(e) => setCommentText(e.target.value)}
                  onKeyDown={(e) => {
                    if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && commentText.trim()) {
                      e.preventDefault();
                      comment.mutate(commentText.trim(), {
                        onError,
                        onSuccess: () => setCommentText(""),
                      });
                    }
                  }}
                  placeholder="Leave an operational note or status update... (Press ⌘+Enter to submit)"
                  className="w-full rounded-xl border border-line bg-canvas/50 p-3 text-sm text-ink placeholder:text-muted focus:border-signal focus:outline-none"
                />
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-muted">Comments do not change item version</span>
                  <button
                    disabled={comment.isPending || !commentText.trim()}
                    className={btnPrimary}
                  >
                    <Send className="size-3.5" />
                    <span>{comment.isPending ? "Posting..." : "Post comment"}</span>
                  </button>
                </div>
              </form>
            )}
          </section>
        </div>

        {/* Right Sidebar Details & AI Widget */}
        <div className="space-y-6">
          {/* Metadata Card */}
          <aside aria-label="Details" className="rounded-2xl border border-line bg-surface p-5 shadow-sm space-y-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-muted">
              Item Details
            </h3>

            <dl className="space-y-3.5 text-xs">
              <DetailRow label="Team">
                <span className="font-medium text-ink">{it.team?.name || it.team_id}</span>
              </DetailRow>

              <DetailRow label="Owner">
                <div className="flex items-center justify-between gap-1 w-full">
                  <span className={it.assignee ? "font-medium text-ink" : "text-muted italic"}>
                    {it.assignee?.name || (it.assignee_id ? "Assigned" : "Unassigned")}
                  </span>
                  {p.can_assign && (
                    <button
                      onClick={() => setAssignModalOpen(true)}
                      className="text-signal hover:underline font-medium"
                    >
                      Assign
                    </button>
                  )}
                </div>
              </DetailRow>

              <DetailRow label="Reporter">
                <span className="text-ink">{it.reporter?.name || it.reporter_id || "System"}</span>
              </DetailRow>

              <DetailRow label="Due Date">
                <span className={it.due_at ? "text-ink font-medium" : "text-muted"}>
                  {it.due_at ? shortDate(it.due_at) : "None set"}
                </span>
              </DetailRow>

              {it.resolution && (
                <DetailRow label="Resolution">
                  <span className="font-semibold text-ink capitalize">
                    {it.resolution.replace("_", " ")}
                    {it.duplicate_of && ` (${it.duplicate_of})`}
                  </span>
                </DetailRow>
              )}

              {it.requires_approval && (
                <DetailRow label="Policy">
                  <span className="inline-flex items-center gap-1 text-p1 font-medium">
                    <ShieldAlert className="size-3" />
                    Lead sign-off required
                  </span>
                </DetailRow>
              )}

              {it.tags && it.tags.length > 0 && (
                <DetailRow label="Tags">
                  <div className="flex flex-wrap gap-1">
                    {it.tags.map((tag) => (
                      <span
                        key={tag}
                        className="rounded-md bg-canvas border border-line px-1.5 py-0.5 text-[11px] text-muted font-mono"
                      >
                        #{tag}
                      </span>
                    ))}
                  </div>
                </DetailRow>
              )}

              <DetailRow label="Last Activity">
                <span className="text-muted">
                  {timeAgo(it.last_activity_at || it.updated_at || it.created_at || "")}
                </span>
              </DetailRow>
            </dl>
          </aside>

          {/* Similar Items Semantic Widget */}
          {similarItemsQuery.data?.items && similarItemsQuery.data.items.length > 0 && (
            <div className="rounded-2xl border border-line bg-surface p-5 shadow-sm space-y-3">
              <div className="flex items-center gap-2">
                <Sparkles className="size-4 text-signal" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-muted">
                  Related Operational Work
                </h3>
              </div>
              <div className="space-y-2">
                {similarItemsQuery.data.items.map((sim) => (
                  <Link
                    key={sim.key}
                    href={`/items/${sim.key}`}
                    className="flex items-center justify-between rounded-xl bg-canvas/60 p-2.5 text-xs hover:bg-canvas border border-line/60 transition-colors"
                  >
                    <div className="min-w-0 flex-1 mr-2">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono font-bold text-signal">{sim.key}</span>
                        <span className="truncate font-medium text-ink">{sim.title}</span>
                      </div>
                    </div>
                    <ChevronRight className="size-3.5 text-muted shrink-0" />
                  </Link>
                ))}
              </div>
            </div>
          )}

          {/* AI Grounded Assistant */}
          <AiAssistantWidget
            itemKey={it.key}
            itemId={it.id || it._id}
            teamId={it.team?.id || it.team_id}
          />
        </div>
      </div>

      {/* Transition Modal with Reason/Resolution */}
      <Modal
        open={transitionModal.open}
        onClose={() => setTransitionModal({ open: false, to: "" })}
        title={`Move to ${transitionModal.to ? STATUS_META[transitionModal.to]?.label : ""}`}
        description="Provide operational justification for auditing and team visibility."
      >
        <div className="space-y-4 pt-2">
          {/* Resolution Selector for resolved and closed */}
          {(transitionModal.to === "resolved" || transitionModal.to === "closed") && (
            <div>
              <label className="block text-xs font-semibold text-ink mb-1">
                Resolution *
              </label>
              <select
                value={transitionResolution}
                onChange={(e) => setTransitionResolution(e.target.value)}
                className="w-full rounded-xl border border-line bg-canvas p-2.5 text-sm text-ink focus:border-signal focus:outline-none"
              >
                <option value="completed">Completed (Work successfully executed)</option>
                <option value="wont_do">Won&apos;t Do (Out of scope or working as expected)</option>
                <option value="duplicate">Duplicate (Duplicated by another item)</option>
                <option value="cancelled">Cancelled (Obsolete or superseded)</option>
              </select>
            </div>
          )}

          {/* Duplicate Of Input */}
          {(transitionModal.to === "resolved" || transitionModal.to === "closed") &&
            transitionResolution === "duplicate" && (
              <div>
                <label className="block text-xs font-semibold text-ink mb-1">
                  Duplicate Of (Item Key) *
                </label>
                <input
                  type="text"
                  placeholder="e.g. PAY-101"
                  value={transitionDuplicateOf}
                  onChange={(e) => setTransitionDuplicateOf(e.target.value.toUpperCase())}
                  className="w-full rounded-xl border border-line bg-canvas p-2.5 text-sm font-mono font-semibold uppercase text-ink placeholder:text-muted focus:border-signal focus:outline-none"
                />
              </div>
            )}

          <div>
            <label className="block text-xs font-semibold text-ink mb-1">
              {transitionModal.to === "blocked" ? "Blocker Reason *" : "Reason / Operational Note"}
            </label>
            <textarea
              rows={3}
              value={transitionReason}
              onChange={(e) => setTransitionReason(e.target.value)}
              placeholder={
                transitionModal.to === "blocked"
                  ? "Describe what is blocking this item (e.g. waiting on external bank partner confirmation)..."
                  : "e.g. User verified refund received, dispute closed..."
              }
              className="w-full rounded-xl border border-line bg-canvas p-3 text-sm text-ink placeholder:text-muted focus:border-signal focus:outline-none"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-line">
            <button
              onClick={() => setTransitionModal({ open: false, to: "" })}
              className={btnSecondary}
            >
              Cancel
            </button>
            <button
              disabled={
                move.isPending ||
                (transitionModal.to === "blocked" && !transitionReason.trim()) ||
                ((transitionModal.to === "resolved" || transitionModal.to === "closed") &&
                  transitionResolution === "duplicate" &&
                  !transitionDuplicateOf.trim())
              }
              onClick={() => {
                if (transitionModal.to) {
                  const isClosingOrResolving =
                    transitionModal.to === "resolved" || transitionModal.to === "closed";
                  move.mutate(
                    {
                      to: transitionModal.to,
                      reason: transitionReason.trim() || undefined,
                      resolution: isClosingOrResolving ? transitionResolution : undefined,
                      duplicate_of:
                        isClosingOrResolving && transitionResolution === "duplicate"
                          ? transitionDuplicateOf.trim()
                          : undefined,
                      version: it.version,
                    },
                    {
                      onError,
                      onSuccess: () => {
                        onOk();
                        setTransitionModal({ open: false, to: "" });
                      },
                    }
                  );
                }
              }}
              className={btnPrimary}
            >
              {move.isPending ? "Transitioning..." : "Confirm status change"}
            </button>
          </div>
        </div>
      </Modal>

      {/* Request Approval Modal */}
      <Modal
        open={approvalModalOpen}
        onClose={() => setApprovalModalOpen(false)}
        title="Request Lead Approval"
        description="Submit this item to the team lead approval queue."
      >
        <div className="space-y-4 pt-2">
          <div>
            <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1">
              Request note *
            </label>
            <textarea
              rows={3}
              value={approvalNote}
              onChange={(e) => setApprovalNote(e.target.value)}
              placeholder="Explain why this exception is ready to be approved..."
              className="w-full rounded-xl border border-line bg-surface p-3 text-sm text-ink focus:border-signal"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2 border-t border-line">
            <button
              onClick={() => setApprovalModalOpen(false)}
              className={btnSecondary}
            >
              Cancel
            </button>
            <button
              disabled={!approvalNote.trim() || requestApproval.isPending}
              onClick={() => {
                requestApproval.mutate(
                  { note: approvalNote.trim(), version: it.version },
                  {
                    onError,
                    onSuccess: () => {
                      onOk();
                      setApprovalModalOpen(false);
                      toast({ tone: "info", text: "Approval requested." });
                    },
                  }
                );
              }}
              className={btnPrimary}
            >
              Submit for approval
            </button>
          </div>
        </div>
      </Modal>

      {/* Lead Decision Modal */}
      <Modal
        open={decisionModal.open}
        onClose={() => setDecisionModal({ open: false, approved: true })}
        title={decisionModal.approved ? "Approve work item" : "Reject approval request"}
        description={
          decisionModal.approved
            ? "Approving this item will transition it to resolved."
            : "Rejecting this item will return it to in-progress for corrective actions."
        }
      >
        <DecisionDialogContent
          approved={decisionModal.approved}
          itemKey={it.key}
          approvalId={it.pending_approval_id || ""}
          onClose={() => setDecisionModal({ open: false, approved: true })}
          onSuccess={() => {
            setDecisionModal({ open: false, approved: true });
            item.refetch();
            tl.refetch();
          }}
        />
      </Modal>

      {/* Assign Member Modal */}
      <Modal
        open={assignModalOpen}
        onClose={() => setAssignModalOpen(false)}
        title="Assign Work Item"
        description="Select a team member to take ownership of this item."
      >
        <AssignMemberDialogContent
          teamId={teamId}
          currentAssigneeId={it.assignee?.id || it.assignee_id || ""}
          version={it.version}
          itemKey={it.key}
          onClose={() => setAssignModalOpen(false)}
          onSuccess={() => {
            setAssignModalOpen(false);
            item.refetch();
          }}
        />
      </Modal>
    </div>
  );
}

const DetailRow = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="flex items-start justify-between gap-2 border-b border-line/40 pb-2">
    <dt className="text-muted shrink-0 w-24">{label}</dt>
    <dd className="text-right flex-1 min-w-0">{children}</dd>
  </div>
);

/** Conflict Panel for Version Concurrency (412) */
function ConflictPanel({ err, onReload }: { err: ApiError; onReload: () => void }) {
  const p = explain(err);
  const changes: TimelineEvent[] = err.problem.meta?.changes_since ?? [];
  return (
    <div role="alert" className="rounded-2xl border border-p1/50 bg-p1/10 p-4 text-xs text-ink space-y-2.5">
      <div className="flex items-center gap-2 font-bold text-p1 text-sm">
        <AlertTriangle className="size-4.5" />
        <span>{p.title}</span>
      </div>
      <p className="text-ink/90 leading-relaxed">{p.message}</p>
      {changes.length > 0 && (
        <div className="pt-2 border-t border-p1/30 space-y-1">
          <p className="font-semibold text-muted text-[11px] uppercase tracking-wider">
            Changes saved by other team members:
          </p>
          <ul className="list-disc pl-4 space-y-1 text-muted">
            {changes.map((c) => (
              <li key={c.id}>
                <span className="font-medium text-ink">{c.actor?.name || "User"}</span>: {describeEvent(c)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {p.actionHint && <p className="text-[11px] font-medium text-signal">Tip: {p.actionHint}</p>}
      <button onClick={onReload} className={`${btnSecondary} mt-2`}>
        Load latest changes
      </button>
    </div>
  );
}

function DecisionDialogContent({
  approved,
  itemKey,
  approvalId,
  onClose,
  onSuccess,
}: {
  approved: boolean;
  itemKey: string;
  approvalId: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [reason, setReason] = useState("");
  const decide = useDecideApproval(approvalId, itemKey);
  const toast = useToast();

  const handleConfirm = async () => {
    try {
      await decide.mutateAsync({ approved, reason: reason.trim() });
      toast({ tone: "info", text: `Item ${approved ? "approved" : "rejected"} successfully.` });
      onSuccess();
    } catch (e) {
      toast(explain(e));
    }
  };

  return (
    <div className="space-y-4 pt-2">
      <div>
        <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1">
          Decision reason / audit note *
        </label>
        <textarea
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder={
            approved
              ? "Confirming verified account balance and customer documentation..."
              : "Missing proof of address or supervisor sign-off..."
          }
          className="w-full rounded-xl border border-line bg-surface p-3 text-sm text-ink focus:border-signal"
        />
      </div>
      <div className="flex justify-end gap-2 pt-2 border-t border-line">
        <button onClick={onClose} className={btnSecondary}>
          Cancel
        </button>
        <button
          disabled={!reason.trim() || decide.isPending}
          onClick={handleConfirm}
          className={approved ? btnSuccess : btnDanger}
        >
          {decide.isPending ? "Submitting..." : approved ? "Confirm approval" : "Confirm rejection"}
        </button>
      </div>
    </div>
  );
}

function AssignMemberDialogContent({
  teamId,
  currentAssigneeId,
  version,
  itemKey,
  onClose,
  onSuccess,
}: {
  teamId: string;
  currentAssigneeId: string;
  version: number;
  itemKey: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const { data: members = [], isLoading } = useTeamMembers(teamId);
  const [selectedId, setSelectedId] = useState(currentAssigneeId);
  const assign = useAssign(itemKey);
  const toast = useToast();

  const handleAssign = async () => {
    try {
      await assign.mutateAsync({
        assignee_id: selectedId || null,
        version,
      });
      toast({ tone: "info", text: "Assignee updated." });
      onSuccess();
    } catch (e) {
      toast(explain(e));
    }
  };

  return (
    <div className="space-y-4 pt-2">
      <div>
        <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1">
          Assignee
        </label>
        {isLoading ? (
          <p className="text-xs text-muted">Loading team members...</p>
        ) : (
          <select
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
            className="w-full rounded-xl border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-signal"
          >
            <option value="">Unassigned</option>
            {members.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name} ({m.role})
              </option>
            ))}
          </select>
        )}
      </div>
      <div className="flex justify-end gap-2 pt-2 border-t border-line">
        <button onClick={onClose} className={btnSecondary}>
          Cancel
        </button>
        <button
          disabled={assign.isPending}
          onClick={handleAssign}
          className={btnPrimary}
        >
          {assign.isPending ? "Assigning..." : "Save assignment"}
        </button>
      </div>
    </div>
  );
}
