"use client";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api, newKey } from "@/lib/api";
import type {
  AiAskResponse,
  AiSimilarItem,
  Approval,
  Bucket,
  Features,
  Item,
  ItemRow,
  Me,
  Notification,
  Page,
  TeamMember,
  TeamMembership,
  TimelineEvent,
} from "@/lib/types";

/** Query keys in one place so invalidation is never a guess. */
export const qk = {
  me: ["me"] as const,
  overview: ["overview"] as const,
  items: (qs: string) => ["items", qs] as const,
  item: (k: string) => ["item", k] as const,
  timeline: (k: string) => ["timeline", k] as const,
  itemSimilar: (k: string) => ["item", k, "similar"] as const,
  teams: ["teams"] as const,
  teamMembers: (teamId: string) => ["teams", teamId, "members"] as const,
  notifications: (unreadOnly?: boolean) => ["notifications", unreadOnly ?? false] as const,
  features: ["meta", "features"] as const,
};

/** After any change to an item: refetch it, its history, and every list that may contain it. */
export const touchItem = (qc: QueryClient, key: string) => {
  qc.invalidateQueries({ queryKey: qk.item(key) });
  qc.invalidateQueries({ queryKey: qk.timeline(key) });
  qc.invalidateQueries({ queryKey: qk.itemSimilar(key) });
  qc.invalidateQueries({ queryKey: ["items"] });
  qc.invalidateQueries({ queryKey: qk.overview });
  qc.invalidateQueries({ queryKey: ["notifications"] });
};

// ── Reads ──────────────────────────────────────────────────────────────

export const useMe = () =>
  useQuery({
    queryKey: qk.me,
    queryFn: () => api<Me>("/auth/me"),
    retry: false,
    staleTime: 5 * 60_000,
  });

export const useOverview = () =>
  useQuery({
    queryKey: qk.overview,
    queryFn: async () => {
      const res = await api<any>("/overview");
      // Handle both { buckets: [...] } format and raw object format
      if (res && Array.isArray(res.buckets)) {
        return { buckets: res.buckets as Bucket[] };
      }

      // Convert backend object format to buckets array
      const bucketConfigs = [
        { key: "awaiting_my_approval", label: "Awaiting your approval" },
        { key: "overdue_mine", label: "Overdue (assigned to you)" },
        { key: "unowned_urgent", label: "Unowned urgent issues" },
        { key: "stale", label: "Stale activity" },
        { key: "blocked_mine", label: "Blocked work" },
      ];

      const buckets: Bucket[] = bucketConfigs.map((cfg) => {
        const raw = res?.[cfg.key] ?? { count: 0, items: [] };
        return {
          key: cfg.key,
          label: cfg.label,
          count: typeof raw.count === "number" ? raw.count : 0,
          capped: (raw.count ?? 0) >= 1000,
          items: Array.isArray(raw.items) ? raw.items : [],
        };
      });

      return { buckets };
    },
  });

export const useItems = (qs: string) =>
  useInfiniteQuery({
    queryKey: qk.items(qs),
    initialPageParam: "",
    queryFn: ({ pageParam }) =>
      api<Page<ItemRow>>(`/items?${qs}${pageParam ? `&cursor=${encodeURIComponent(pageParam)}` : ""}`),
    getNextPageParam: (p) => p.next_cursor ?? undefined,
  });

export const useItem = (key: string) =>
  useQuery({
    queryKey: qk.item(key),
    queryFn: () => api<Item>(`/items/${key}`),
    enabled: Boolean(key),
  });

export const useTimeline = (key: string) =>
  useQuery({
    queryKey: qk.timeline(key),
    queryFn: async () => {
      const res = await api<any>(`/items/${key}/timeline`);
      const events: TimelineEvent[] = res?.events ?? res?.items ?? [];
      return { items: events, next_cursor: res?.next_cursor ?? null, has_more: Boolean(res?.has_more) };
    },
    enabled: Boolean(key),
  });

export const useTeams = () =>
  useQuery({
    queryKey: qk.teams,
    queryFn: () => api<TeamMembership[]>("/teams"),
  });

export const useTeamMembers = (teamId?: string) =>
  useQuery({
    queryKey: qk.teamMembers(teamId ?? ""),
    queryFn: () => api<TeamMember[]>(`/teams/${teamId}/members`),
    enabled: Boolean(teamId),
  });

export const useFeatures = () =>
  useQuery({
    queryKey: qk.features,
    queryFn: () => api<Features>("/meta/features"),
    staleTime: 10 * 60_000,
  });

export const useItemSimilar = (key: string) =>
  useQuery({
    queryKey: qk.itemSimilar(key),
    queryFn: () => api<{ items: AiSimilarItem[] }>(`/items/${key}/similar?limit=4`),
    enabled: Boolean(key),
  });

export const useNotifications = (unreadOnly = false) =>
  useQuery({
    queryKey: qk.notifications(unreadOnly),
    queryFn: () => api<Notification[]>(`/notifications?unread_only=${unreadOnly}`),
    refetchInterval: 30_000,
  });

// ── Writes (Mutations with Idempotency-Key and Optimistic Concurrency) ──

export function useClaim(key: string, me?: Me) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (idem: string) =>
      api<Item>(`/items/${key}/claim`, { method: "POST", key: idem }),
    onMutate: async () => {
      await qc.cancelQueries({ queryKey: qk.item(key) });
      const prev = qc.getQueryData<Item>(qk.item(key));
      if (prev && me) {
        qc.setQueryData<Item>(qk.item(key), {
          ...prev,
          assignee: me.user,
          assignee_id: me.user.id,
          permissions: { ...prev.permissions, can_claim: false, can_release: true },
        });
      }
      return { prev };
    },
    onError: (_e, _v, ctx) => ctx?.prev && qc.setQueryData(qk.item(key), ctx.prev),
    onSettled: () => touchItem(qc, key),
  });
}

export function useRelease(key: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api<Item>(`/items/${key}/release`, { method: "POST", key: newKey() }),
    onSettled: () => touchItem(qc, key),
  });
}

export const useAssign = (key: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { assignee_id: string | null; version: number }) =>
      api<Item>(`/items/${key}/assign`, {
        method: "POST",
        key: newKey(),
        version: v.version,
        body: { assignee_id: v.assignee_id },
      }),
    onSettled: () => touchItem(qc, key),
  });
};

export const useTransition = (key: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { to: string; reason?: string; resolution?: string; duplicate_of?: string; version: number }) =>
      api<Item>(`/items/${key}/transitions`, {
        method: "POST",
        key: newKey(),
        version: v.version,
        body: {
          to: v.to,
          to_status: v.to, // satisfies both contract styles
          reason: v.reason || undefined,
          resolution: v.resolution || undefined,
          duplicate_of: v.duplicate_of || undefined,
        },
      }),
    onSettled: () => touchItem(qc, key),
  });
};

export const useComment = (key: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: string) =>
      api(`/items/${key}/comments`, { method: "POST", key: newKey(), body: { body } }),
    onSettled: () => touchItem(qc, key),
  });
};

export const usePatchItem = (key: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: {
      patch: Partial<Pick<Item, "priority" | "title" | "description" | "tags" | "due_at">>;
      version: number;
    }) =>
      api<Item>(`/items/${key}`, { method: "PATCH", version: v.version, body: v.patch }),
    onSettled: () => touchItem(qc, key),
  });
};

export const useRequestApproval = (key: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { note: string; version: number }) =>
      api<Approval>(`/items/${key}/approval`, {
        method: "POST",
        key: newKey(),
        version: v.version,
        body: { request_note: v.note },
      }),
    onSettled: () => touchItem(qc, key),
  });
};

export const useDecideApproval = (approvalId: string, itemKey: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { approved: boolean; reason: string }) =>
      api(`/approvals/${approvalId}/decision`, {
        method: "POST",
        key: newKey(),
        body: { approved: v.approved, decision_reason: v.reason },
      }),
    onSettled: () => touchItem(qc, itemKey),
  });
};

export const useCreateItem = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      team_id: string;
      title: string;
      description?: string;
      type?: string;
      priority?: string;
      due_at?: string | null;
      tags?: string[];
    }) =>
      api<Item>("/items", {
        method: "POST",
        key: newKey(),
        body: payload,
      }),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["items"] });
      qc.invalidateQueries({ queryKey: qk.overview });
    },
  });
};

export const useSimilarQuery = () =>
  useMutation({
    mutationFn: (payload: { title: string; description?: string; team_id?: string }) =>
      api<{ items: AiSimilarItem[] }>("/ai/similar", {
        method: "POST",
        body: payload,
      }),
  });

export const useAskAi = () =>
  useMutation({
    mutationFn: (payload: { question: string; item_id?: string; team_id?: string }) =>
      api<AiAskResponse>("/ai/ask", {
        method: "POST",
        body: payload,
      }),
  });

export const useMarkNotificationRead = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api(`/notifications/${id}/read`, { method: "POST" }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
};

export const useMarkAllNotificationsRead = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api("/notifications/read-all", { method: "POST" }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
};
