"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertCircle, AlertTriangle, Check, Loader2, Sparkles, X } from "lucide-react";
import { Modal, btnPrimary, btnSecondary } from "./ui";
import { useCreateItem, useMe, useSimilarQuery } from "@/hooks/items";
import { useToast } from "./toast";
import { explain } from "@/lib/errors";
import { ITEM_TYPE_META, PRIORITY_META } from "@/lib/constants";
import type { AiSimilarItem, Priority } from "@/lib/types";

const schema = z.object({
  team_id: z.string().min(1, "Please select a team"),
  title: z.string().min(3, "Title must be at least 3 characters").max(200),
  description: z.string().max(20000).optional(),
  type: z.enum(["customer_issue", "payment", "compliance", "system_alert", "access_request"]),
  priority: z.enum(["P0", "P1", "P2", "P3"]),
  due_at: z.string().optional(),
  tags: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

export function CreateItemDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const toast = useToast();
  const me = useMe();
  const createItem = useCreateItem();
  const similarQuery = useSimilarQuery();

  const [similarItems, setSimilarItems] = useState<AiSimilarItem[]>([]);
  const userTeams = me.data?.teams ?? [];

  const defaultTeam = userTeams[0]?.team_id || "";

  const {
    register,
    handleSubmit,
    watch,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      team_id: defaultTeam,
      title: "",
      description: "",
      type: "customer_issue",
      priority: "P2",
      due_at: "",
      tags: "",
    },
  });

  const selectedTeamId = watch("team_id");
  const currentTitle = watch("title");
  const currentDescription = watch("description");

  // Check if current user is lead in selected team
  const isLeadInSelectedTeam =
    me.data?.is_org_admin ||
    userTeams.some((t) => (t.team_id === selectedTeamId || t.team?.id === selectedTeamId) && t.role === "lead");

  // Debounced AI duplicate check
  useEffect(() => {
    if (!currentTitle || currentTitle.trim().length < 5) {
      setSimilarItems([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const res = await similarQuery.mutateAsync({
          title: currentTitle.trim(),
          description: currentDescription?.trim() || undefined,
          team_id: selectedTeamId || undefined,
        });
        setSimilarItems(res.items.filter((i) => i.score > 0.65));
      } catch {
        // AI query is non-blocking
        setSimilarItems([]);
      }
    }, 600);
    return () => clearTimeout(timer);
  }, [currentTitle, currentDescription, selectedTeamId]);

  const onSubmit = async (values: FormValues) => {
    try {
      const parsedTags = values.tags
        ? values.tags
            .split(",")
            .map((t) => t.trim().toLowerCase())
            .filter(Boolean)
        : [];

      const isoDue = values.due_at ? new Date(values.due_at).toISOString() : null;

      const created = await createItem.mutateAsync({
        team_id: values.team_id,
        title: values.title,
        description: values.description || "",
        type: values.type,
        priority: values.priority,
        due_at: isoDue,
        tags: parsedTags,
      });

      toast({ tone: "info", text: `Item ${created.key} created successfully.` });
      reset();
      onClose();
      router.push(`/items/${created.key}`);
    } catch (err) {
      toast(explain(err));
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Create operational item"
      description="Track a customer ticket, payment exception, system alert, or compliance review."
      maxWidth="max-w-xl"
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 pt-1">
        {/* Team Selection */}
        <div>
          <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1">
            Team *
          </label>
          <select
            {...register("team_id")}
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-signal"
          >
            {userTeams.map((t) => {
              const id = t.team_id || t.team?.id || "";
              const name = t.team_name || t.team?.name || id;
              return (
                <option key={id} value={id}>
                  {name} ({t.role})
                </option>
              );
            })}
          </select>
          {errors.team_id && <p className="mt-1 text-xs text-p0">{errors.team_id.message}</p>}
        </div>

        {/* Title */}
        <div>
          <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1">
            Title *
          </label>
          <input
            type="text"
            placeholder="e.g. Wire transfer delay for merchant ACME-902"
            {...register("title")}
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-signal"
          />
          {errors.title && <p className="mt-1 text-xs text-p0">{errors.title.message}</p>}
        </div>

        {/* AI Duplicate Detection Banner */}
        {similarItems.length > 0 && (
          <div className="rounded-xl border border-p1/40 bg-p1/10 p-3 text-xs text-ink animate-in fade-in-0 duration-200">
            <div className="flex items-center gap-1.5 font-semibold text-p1 mb-1.5">
              <Sparkles className="size-4" />
              Similar items already exist
            </div>
            <p className="text-muted mb-2">
              Before creating a duplicate, check if one of these items addresses the issue:
            </p>
            <div className="space-y-1.5 max-h-32 overflow-y-auto">
              {similarItems.map((item) => (
                <button
                  type="button"
                  key={item.key}
                  onClick={() => {
                    onClose();
                    router.push(`/items/${item.key}`);
                  }}
                  className="flex w-full items-center justify-between rounded-lg bg-surface/80 p-2 text-left hover:bg-surface border border-line/60 transition-colors"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-mono font-semibold text-signal">{item.key}</span>
                    <span className="truncate font-medium">{item.title}</span>
                  </div>
                  <span className="shrink-0 text-muted ml-2">
                    {Math.round(item.score * 100)}% match
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Type & Priority Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1">
              Type
            </label>
            <select
              {...register("type")}
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-signal"
            >
              {Object.entries(ITEM_TYPE_META).map(([val, meta]) => (
                <option key={val} value={val}>
                  {meta.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1">
              Priority
            </label>
            <select
              {...register("priority")}
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-signal"
            >
              <option value="P0" disabled={!isLeadInSelectedTeam}>
                P0 · Critical {!isLeadInSelectedTeam ? "(Lead only)" : ""}
              </option>
              <option value="P1">P1 · High</option>
              <option value="P2">P2 · Normal</option>
              <option value="P3">P3 · Low</option>
            </select>
          </div>
        </div>

        {/* Description */}
        <div>
          <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1">
            Description
          </label>
          <textarea
            rows={4}
            placeholder="Provide context, customer impact, steps taken, or reference IDs..."
            {...register("description")}
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-signal"
          />
          {errors.description && (
            <p className="mt-1 text-xs text-p0">{errors.description.message}</p>
          )}
        </div>

        {/* Due Date & Tags */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1">
              Due date (optional)
            </label>
            <input
              type="datetime-local"
              {...register("due_at")}
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-signal"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-1">
              Tags (comma separated)
            </label>
            <input
              type="text"
              placeholder="e.g. refund, wire, tier1"
              {...register("tags")}
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-signal"
            />
          </div>
        </div>

        {/* Modal actions */}
        <div className="flex items-center justify-end gap-3 pt-4 border-t border-line">
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting || createItem.isPending}
            className={btnSecondary}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isSubmitting || createItem.isPending}
            className={btnPrimary}
          >
            {(isSubmitting || createItem.isPending) && (
              <Loader2 className="size-4 animate-spin" />
            )}
            Create item
          </button>
        </div>
      </form>
    </Modal>
  );
}
