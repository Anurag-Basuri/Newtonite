import { ApiError } from "./api";

export type ProcessedError = {
  tone: "error" | "warn" | "info";
  title: string;
  message: string;
  text: string; // backward-compatibility alias for message
  fieldErrors?: Record<string, string>;
  actionHint?: string;
  code: string;
  status: number;
  requestId?: string;
  meta?: Record<string, any>;
};

// Backward compatibility Notice type
export type Notice = ProcessedError;

/**
 * Intelligent error processing engine.
 * Converts raw server errors, network dropouts, validation exceptions,
 * and concurrency conflicts into clear, human-understandable diagnostics
 * with actionable recovery hints.
 */
export function explain(e: unknown): ProcessedError {
  // 1. Handle non-ApiError cases (e.g. unknown JavaScript exceptions)
  if (!(e instanceof ApiError)) {
    const rawMsg = e instanceof Error ? e.message : String(e);

    if (rawMsg.includes("Failed to fetch") || rawMsg.includes("NetworkError") || rawMsg.includes("fetch failed")) {
      return {
        tone: "error",
        title: "Backend Server Offline",
        message: "Cannot connect to the Opsboard backend server. Please verify the API server is running on http://localhost:8000.",
        text: "Cannot connect to the Opsboard backend server. Please verify the API server is running on http://localhost:8000.",
        actionHint: "Start the backend server (e.g., `uvicorn app.main:app` or `make up`) and refresh.",
        code: "SERVER_OFFLINE",
        status: 0,
      };
    }

    return {
      tone: "error",
      title: "Unexpected Client Error",
      message: rawMsg || "An unexpected error occurred in the browser.",
      text: rawMsg || "An unexpected error occurred in the browser.",
      actionHint: "Please reload the page or check the browser console for details.",
      code: "CLIENT_ERROR",
      status: 0,
    };
  }

  const { status, code, detail, problem, meta, errors, requestId, path } = e;
  const rawDetail = detail || problem.detail || problem.title || "";

  // 2. Server offline / Connection refused / Next.js proxy 502
  if (
    status === 0 ||
    code === "SERVER_UNREACHABLE" ||
    code === "SERVER_OFFLINE" ||
    [502, 503, 504].includes(status)
  ) {
    return {
      tone: "error",
      title: "Backend Server Not Running",
      message: "The backend server is not responding at http://localhost:8000. Opsboard cannot process your request while the API is offline.",
      text: "The backend server is not responding at http://localhost:8000. Opsboard cannot process your request while the API is offline.",
      actionHint: "Ensure the backend FastAPI service is running locally on port 8000.",
      code: "SERVER_OFFLINE",
      status,
      requestId,
    };
  }

  // 3. Authentication & Sign-in (401)
  if (status === 401 || code === "UNAUTHENTICATED") {
    const isLoginEndpoint = path?.includes("/auth/login");
    if (isLoginEndpoint) {
      return {
        tone: "error",
        title: "Invalid Credentials",
        message: "The work email or password entered does not match our records. Please verify your credentials.",
        text: "The work email or password entered does not match our records. Please verify your credentials.",
        actionHint: "Check for typos or use one of the 1-click demo logins below (e.g., Priya Lead).",
        code: "INVALID_CREDENTIALS",
        status,
        requestId,
      };
    }
    return {
      tone: "warn",
      title: "Session Expired",
      message: "Your authenticated session has ended or is no longer valid. Please sign in again to continue.",
      text: "Your authenticated session has ended or is no longer valid. Please sign in again to continue.",
      actionHint: "Sign in with your work email to regain access.",
      code: "SESSION_EXPIRED",
      status,
      requestId,
    };
  }

  // 4. Schema / Form Validation (422)
  if (status === 422 || code === "VALIDATION_FAILED" || code === "VALIDATION_ERROR") {
    const fieldErrors: Record<string, string> = {};
    const fieldSummaries: string[] = [];

    if (Array.isArray(errors) && errors.length > 0) {
      for (const err of errors) {
        const field = err.loc && err.loc.length > 0 ? String(err.loc[err.loc.length - 1]) : "general";
        let humanMsg = err.msg || "Invalid value";

        // Translate Pydantic validation errors into clean user messages
        if (humanMsg.includes("String should have at least")) {
          const minMatch = humanMsg.match(/at least (\d+)/);
          humanMsg = `Must be at least ${minMatch ? minMatch[1] : "3"} characters long.`;
        } else if (humanMsg.includes("value is not a valid email")) {
          humanMsg = "Please enter a valid work email address (e.g. name@company.com).";
        } else if (humanMsg.includes("Field required")) {
          humanMsg = "This field cannot be left blank.";
        } else if (humanMsg.includes("Input should be")) {
          humanMsg = "Please select a valid option from the list.";
        }

        fieldErrors[field] = humanMsg;
        fieldSummaries.push(`${field}: ${humanMsg}`);
      }
    }

    const summaryText =
      fieldSummaries.length > 0
        ? `Please check the following fields: ${fieldSummaries.join(" · ")}`
        : rawDetail || "Some submitted fields contain invalid values. Please review and correct them.";

    return {
      tone: "error",
      title: "Validation Issue",
      message: summaryText,
      text: summaryText,
      fieldErrors,
      actionHint: "Correct the highlighted fields above and submit again.",
      code: "VALIDATION_FAILED",
      status,
      requestId,
    };
  }

  // 5. Permission / Authorization (403)
  if (status === 403 || code === "FORBIDDEN") {
    let msg = rawDetail;
    let hint = "Contact your team lead or an organization admin if you need access.";

    if (rawDetail.toLowerCase().includes("p0") || rawDetail.toLowerCase().includes("lead")) {
      msg = "Only designated team leads have authority to assign priority P0 or reassign items.";
      hint = "Request a lead on your team to review and escalate this item.";
    } else if (rawDetail.toLowerCase().includes("viewer")) {
      msg = "Your account has read-only viewer permissions in this team and cannot make changes.";
      hint = "Contact an admin to upgrade your role to member if you need editing rights.";
    } else if (!msg) {
      msg = "You do not have the required permissions to perform this action in this team.";
    }

    return {
      tone: "error",
      title: "Access Restricted",
      message: msg,
      text: msg,
      actionHint: hint,
      code: "FORBIDDEN",
      status,
      requestId,
    };
  }

  // 6. Not Found (404)
  if (status === 404 || code === "NOT_FOUND") {
    return {
      tone: "warn",
      title: "Item Not Found",
      message: "The requested item or team could not be found, or it is outside your assigned teams.",
      text: "The requested item or team could not be found, or it is outside your assigned teams.",
      actionHint: "Double check the item key (e.g. PAY-143) or check your team memberships.",
      code: "NOT_FOUND",
      status,
      requestId,
    };
  }

  // 7. State & Concurrency Conflicts (409 & 412)
  if (code === "ALREADY_CLAIMED") {
    const winnerName = meta?.winner_name || meta?.assignee?.name || meta?.winner_id;
    const msg = winnerName
      ? `Another team member (${winnerName}) claimed ownership of this item moments before you.`
      : "Another team member has already claimed ownership of this item.";
    return {
      tone: "warn",
      title: "Item Already Claimed",
      message: msg,
      text: msg,
      actionHint: "Reload the item to see the current assignee and status.",
      code,
      status,
      requestId,
      meta,
    };
  }

  if (status === 412 || code === "VERSION_CONFLICT") {
    return {
      tone: "warn",
      title: "Concurrent Edit Detected",
      message: "Someone else saved changes to this item while you had it open. Your modifications were not saved to prevent overwriting their work.",
      text: "Someone else saved changes to this item while you had it open. Your modifications were not saved to prevent overwriting their work.",
      actionHint: "Review the concurrent changes in the diff panel below, then reload the latest version.",
      code: "VERSION_CONFLICT",
      status,
      requestId,
      meta,
    };
  }

  if (code === "FOUR_EYES_VIOLATION") {
    return {
      tone: "warn",
      title: "Four-Eyes Policy Required",
      message: "Regulatory compliance rule: You cannot approve or sign off on an approval request you personally submitted.",
      text: "Regulatory compliance rule: You cannot approve or sign off on an approval request you personally submitted.",
      actionHint: "A different team lead must review and decide this approval.",
      code,
      status,
      requestId,
    };
  }

  if (code === "APPROVAL_PENDING") {
    return {
      tone: "warn",
      title: "Approval Already Pending",
      message: "An approval request is already open and waiting for a team lead to review.",
      text: "An approval request is already open and waiting for a team lead to review.",
      actionHint: "Wait for the pending approval to be resolved before requesting another.",
      code,
      status,
      requestId,
    };
  }

  if (code === "ITEM_CLOSED") {
    return {
      tone: "warn",
      title: "Item is Closed",
      message: "This work item has already been marked as closed and cannot be edited or moved.",
      text: "This work item has already been marked as closed and cannot be edited or moved.",
      actionHint: "Create a new work item if follow-up work is required.",
      code,
      status,
      requestId,
    };
  }

  if (code === "INVALID_TRANSITION") {
    const allowed = Array.isArray(meta?.allowed) ? meta.allowed.join(", ") : "";
    const msg = allowed
      ? `This status change is not allowed from the current state. Permitted next steps: ${allowed}.`
      : "This status change is not permitted from the item's current state.";
    return {
      tone: "warn",
      title: "Invalid Status Move",
      message: msg,
      text: msg,
      actionHint: allowed ? `Select one of: ${allowed}` : "Review the item workflow.",
      code,
      status,
      requestId,
      meta,
    };
  }

  // 8. Rate Limiting (429)
  if (status === 429 || code === "RATE_LIMITED") {
    return {
      tone: "warn",
      title: "Request Rate Limit Exceeded",
      message: "Too many requests were sent in a short interval. The server is temporarily throttling requests.",
      text: "Too many requests were sent in a short interval. The server is temporarily throttling requests.",
      actionHint: "Please wait 5 to 10 seconds before trying again.",
      code: "RATE_LIMITED",
      status,
      requestId,
    };
  }

  // 9. Precondition Required (428)
  if (status === 428 || code === "PRECONDITION_REQUIRED") {
    return {
      tone: "warn",
      title: "Missing Version Precondition",
      message: "The request did not supply the required version header (If-Match) to guarantee concurrency safety.",
      text: "The request did not supply the required version header (If-Match) to guarantee concurrency safety.",
      actionHint: "Reload the item to get the latest version token.",
      code: "PRECONDITION_REQUIRED",
      status,
      requestId,
    };
  }

  // 10. AI Unavailable (503)
  if (code === "AI_DISABLED" || code === "AI_UNAVAILABLE") {
    return {
      tone: "info",
      title: "AI Service Not Available",
      message: "AI semantic search and question answering features are currently disabled in this environment.",
      text: "AI semantic search and question answering features are currently disabled in this environment.",
      actionHint: "Enable AI_ENABLED in the backend configuration to use this feature.",
      code,
      status,
      requestId,
    };
  }

  // 11. Internal Server Error (500)
  if (status === 500 || code === "INTERNAL_ERROR") {
    return {
      tone: "error",
      title: "Internal Server Error",
      message: `An unexpected issue occurred inside the server${requestId ? ` (Reference ID: ${requestId})` : ""}.`,
      text: `An unexpected issue occurred inside the server${requestId ? ` (Reference ID: ${requestId})` : ""}.`,
      actionHint: "The error has been logged. Please try again in a few moments.",
      code: "INTERNAL_ERROR",
      status,
      requestId,
    };
  }

  // 12. Fallback for other codes
  return {
    tone: "error",
    title: problem.title || `Error ${status}`,
    message: rawDetail || `The server returned an error (HTTP ${status}).`,
    text: rawDetail || `The server returned an error (HTTP ${status}).`,
    actionHint: "Please retry or contact support if the issue persists.",
    code,
    status,
    requestId,
  };
}

export const isVersionConflict = (e: unknown): e is ApiError =>
  e instanceof ApiError && (e.status === 412 || e.code === "VERSION_CONFLICT");

export const isServerOffline = (e: unknown): boolean =>
  e instanceof ApiError &&
  (e.status === 0 || e.code === "SERVER_OFFLINE" || e.code === "SERVER_UNREACHABLE");
