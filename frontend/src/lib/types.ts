export type Priority = "P0" | "P1" | "P2" | "P3";
export type Status = "open" | "triaged" | "in_progress" | "blocked" | "pending_approval" | "resolved" | "closed";
export type ItemType =
  | "customer_issue"
  | "engineering"
  | "payment"
  | "incident"
  | "compliance"
  | "task"
  | "system_alert"
  | "access_request"
  | string;

export type UserRef = { id: string; name: string; email?: string };

export type ItemRow = {
  id?: string;
  _id?: string;
  key: string;
  title: string;
  type: ItemType;
  priority: Priority;
  status: Status;
  team?: { id: string; name: string; key_prefix: string };
  team_id?: string;
  assignee?: UserRef | null;
  assignee_id?: string | null;
  reporter?: UserRef;
  reporter_id?: string;
  due_at?: string | null;
  attention_due_at?: string | null;
  version: number;
  last_activity_at?: string;
  created_at?: string;
  updated_at?: string;
  attention?: ("overdue" | "stale")[];
  pending_approval_id?: string | null;
};

export type Item = ItemRow & {
  description: string;
  requires_approval?: boolean;
  tags: string[];
  resolution?: string | null;
  duplicate_of?: string | null;
  permissions: {
    can_edit: boolean;
    can_claim: boolean;
    can_release?: boolean;
    can_assign: boolean;
    can_comment: boolean;
    allowed_transitions: Status[];
  };
};

export type TimelineEvent = {
  id: string;
  seq: number;
  type: string;
  actor: UserRef;
  at: string;
  item_version: number;
  payload: Record<string, any>;
};

export type Page<T> = { items: T[]; next_cursor: string | null; has_more: boolean };

export type TeamMembership = {
  team_id: string;
  team_name?: string;
  slug?: string;
  role: "viewer" | "member" | "lead";
  key_prefix?: string;
  team?: { id: string; name: string; key_prefix?: string };
};

export type Me = {
  user: UserRef;
  is_org_admin: boolean;
  teams: TeamMembership[];
};

export type Bucket = { key: string; label: string; count: number; capped: boolean; items: ItemRow[] };

export type Problem = {
  code: string;
  title: string;
  detail?: string;
  status: number;
  request_id?: string;
  meta?: Record<string, any>;
};

export type Notification = {
  id: string;
  user_id: string;
  title: string;
  body: string;
  item_key?: string;
  item_id?: string;
  read: boolean;
  created_at: string;
  kind?: string;
};

export type Approval = {
  id: string;
  item_id: string;
  status: "pending" | "approved" | "rejected" | "cancelled";
  requested_by: UserRef | string;
  requested_at: string;
  request_note?: string;
  decided_by?: UserRef | string | null;
  decided_at?: string | null;
  decision_reason?: string | null;
};

export type AiSimilarItem = {
  key: string;
  title: string;
  status: Status;
  priority: Priority;
  assignee?: string | null;
  score: number;
};

export type AiAskCitation = {
  marker: string;
  item_key: string;
  item_id: string;
  kind: string;
  snippet: string;
  url: string;
};

export type AiAskResponse = {
  question: string;
  answer: string | null;
  degraded: boolean;
  citations: AiAskCitation[];
  retrieved: { marker: string; item_key: string; kind: string; score: number; text: string }[];
  timings_ms?: Record<string, any>;
};

export type Features = {
  ai_enabled: boolean;
  llm_enabled: boolean;
  search_mode: string;
};

export type TeamMember = {
  id: string;
  user_id?: string;
  team_id?: string;
  role: "viewer" | "member" | "lead";
  name?: string;
  email?: string;
  user?: {
    id: string;
    name: string;
    email?: string;
  };
};
