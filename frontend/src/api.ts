const BASE = "/api/v1";
const KEY = "sahaayak_token";

export const tokenStore = {
  get: () => sessionStorage.getItem(KEY),
  set: (t: string) => sessionStorage.setItem(KEY, t),
  clear: () => sessionStorage.removeItem(KEY),
};

export class ApiError extends Error {
  status: number;
  suggestions: string[];
  constructor(status: number, message: string, suggestions: string[] = []) {
    super(message);
    this.status = status;
    this.suggestions = suggestions;
  }
}

export function parseDetail(detail: unknown, status: number): { message: string; suggestions: string[] } {
  if (typeof detail === "string") return { message: detail, suggestions: [] };
  if (Array.isArray(detail)) {
    const message = detail
      .map((d: { loc?: unknown[]; msg?: string }) => {
        const loc = (d.loc ?? []).filter((x) => x !== "body").join(".");
        const msg = String(d.msg ?? "Invalid value").replace(/^Value error, /, "");
        return loc ? `${loc}: ${msg}` : msg;
      })
      .join("; ");
    return { message, suggestions: [] };
  }
  if (detail && typeof detail === "object") {
    const d = detail as { message?: string; suggestions?: string[] };
    return { message: d.message ?? "Request failed.", suggestions: d.suggestions ?? [] };
  }
  return { message: `Request failed (${status}).`, suggestions: [] };
}

let onUnauthorized: (() => void) | null = null;
export const setUnauthorizedHandler = (fn: (() => void) | null) => { onUnauthorized = fn; };

type Query = Record<string, string | number | boolean | null | undefined>;
interface Options { method?: string; body?: unknown; form?: Record<string, string>; query?: Query }

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const url = new URL(BASE + path, window.location.origin);
  for (const [k, v] of Object.entries(opts.query ?? {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  const headers: Record<string, string> = {};
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.form) body = new URLSearchParams(opts.form);
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(url, { method: opts.method ?? (body ? "POST" : "GET"), headers, body });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check your connection and try again.");
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && token && onUnauthorized) onUnauthorized();
    if (res.status === 429) throw new ApiError(429, "Too many attempts. Please wait a minute and try again.");
    const p = parseDetail(data?.detail, res.status);
    throw new ApiError(res.status, p.message, p.suggestions);
  }
  return data as T;
}