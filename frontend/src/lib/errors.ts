import { ApiError } from "./api";

export type Notice = { tone: "error" | "warn" | "info"; text: string };

/** The one place that turns server error codes into plain-language messages. The server decides; the UI explains. */
export function explain(e: unknown): Notice {
  if (!(e instanceof ApiError)) {
    return { tone: "error", text: "Couldn’t reach the server. Check your connection and try again." };
  }
  const m = e.problem.meta ?? {};
  switch (e.code) {
    case "ALREADY_CLAIMED":
      return { tone: "warn", text: `${m.assignee?.name ?? "Another team member"} took this first.` };
    case "VERSION_CONFLICT":
      return { tone: "warn", text: "Someone changed this while you were looking. Your change wasn’t saved." };
    case "INVALID_TRANSITION":
      return { tone: "warn", text: "That step isn’t available from the current status." };
    case "FOUR_EYES_VIOLATION":
      return { tone: "warn", text: "Four-eyes rule: You cannot approve a request you submitted." };
    case "APPROVAL_PENDING":
      return { tone: "warn", text: "An approval request is already pending for this item." };
    case "ITEM_CLOSED":
      return { tone: "warn", text: "This item is closed and cannot be modified." };
    case "FORBIDDEN":
      return { tone: "error", text: e.problem.detail || "You don’t have permission to perform that action." };
    case "UNAUTHENTICATED":
      return { tone: "error", text: "Your session has expired. Please sign in again." };
    case "RATE_LIMITED":
      return { tone: "warn", text: "Too many requests. Wait a moment and try again." };
    case "AI_DISABLED":
      return { tone: "info", text: "AI capabilities are currently disabled in this environment." };
    case "BAD_CURSOR":
      return { tone: "warn", text: "Pagination expired. Returning to top of list." };
    default:
      return { tone: "error", text: e.problem.detail ?? e.problem.title ?? "An unexpected error occurred." };
  }
}

export const isVersionConflict = (e: unknown): e is ApiError => e instanceof ApiError && e.code === "VERSION_CONFLICT";
