import type { Problem } from "./types";

export class ApiError extends Error {
  public code: string;
  public detail?: string;
  public errors?: Array<{ loc?: string[]; msg?: string; type?: string }>;
  public meta?: Record<string, any>;
  public requestId?: string;
  public path?: string;
  public method?: string;

  constructor(
    public status: number,
    public problem: Problem,
    extra?: { path?: string; method?: string }
  ) {
    const message = problem.detail || problem.title || "An error occurred";
    super(message);
    this.name = "ApiError";
    this.code = problem.code || "UNKNOWN";
    this.detail = problem.detail;
    this.errors = (problem as any).errors;
    this.meta = problem.meta;
    this.requestId = problem.request_id;
    this.path = extra?.path;
    this.method = extra?.method;
  }
}

export const newKey = () => crypto.randomUUID();

type Opts = {
  method?: string;
  body?: unknown;
  key?: string;
  version?: number;
  signal?: AbortSignal;
};

/**
 * Universal fetch wrapper adhering strictly to:
 * - RFC 7807 Problem Details
 * - Idempotency-Key
 * - If-Match optimistic concurrency
 * - Intelligent network & server offline error detection
 */
export async function api<T>(path: string, o: Opts = {}): Promise<T> {
  const method = o.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (o.body !== undefined) headers["Content-Type"] = "application/json";
  if (o.key) headers["Idempotency-Key"] = o.key;
  if (o.version !== undefined) headers["If-Match"] = `"${o.version}"`;
  if (method !== "GET") headers["X-Requested-With"] = "opsboard";

  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, {
      method,
      headers,
      signal: o.signal,
      credentials: "same-origin",
      body: o.body !== undefined ? JSON.stringify(o.body) : undefined,
    });
  } catch (networkErr: any) {
    // Detect network / connection refused / offline errors
    const isAbort = networkErr?.name === "AbortError";
    const code = isAbort ? "REQUEST_ABORTED" : "SERVER_UNREACHABLE";
    const title = isAbort ? "Request Aborted" : "Backend Server Unreachable";
    const detail = isAbort
      ? "The request was cancelled or timed out."
      : "Could not connect to the backend server at http://localhost:8000. Please ensure the backend server is running.";

    throw new ApiError(
      0,
      { code, title, detail, status: 0 },
      { path, method }
    );
  }

  if (res.status === 204) return undefined as T;

  const data = await res.json().catch(() => null);

  if (!res.ok) {
    // If Next.js rewrite returned a 502/503/504 gateway error because backend is down
    if ([502, 503, 504].includes(res.status) && !data?.code) {
      throw new ApiError(
        res.status,
        {
          code: "SERVER_OFFLINE",
          title: "Backend Server Offline",
          detail: "The proxy server could not reach the backend API at http://localhost:8000. Make sure the backend server is running.",
          status: res.status,
        },
        { path, method }
      );
    }

    throw new ApiError(
      res.status,
      data ?? {
        code: `HTTP_${res.status}`,
        title: res.statusText || "Request Failed",
        detail: `The server returned error ${res.status}.`,
        status: res.status,
      },
      { path, method }
    );
  }

  return data as T;
}
