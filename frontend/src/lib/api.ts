import type { Problem } from "./types";
export class ApiError extends Error {
  constructor(public status: number, public problem: Problem) { super(problem.detail ?? problem.title); }
  get code() { return this.problem.code; }
}
export const newKey = () => crypto.randomUUID();
type Opts = { method?: string; body?: unknown; key?: string; version?: number; signal?: AbortSignal };

/** One fetch wrapper = one place that knows the contract: Problem Details, Idempotency-Key, If-Match. */
export async function api<T>(path: string, o: Opts = {}): Promise<T> {
  const method = o.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (o.body !== undefined) headers["Content-Type"] = "application/json";
  if (o.key) headers["Idempotency-Key"] = o.key;
  if (o.version !== undefined) headers["If-Match"] = `"${o.version}"`;
  if (method !== "GET") headers["X-Requested-With"] = "opsboard";
  const res = await fetch(`/api/v1${path}`, {
    method, headers, signal: o.signal, credentials: "same-origin",
    body: o.body !== undefined ? JSON.stringify(o.body) : undefined,
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, data ?? { code: "UNKNOWN", title: res.statusText, status: res.status });
  return data as T;
}
