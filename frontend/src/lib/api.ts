/** Thin, typed fetch wrapper.
 *  - same-origin cookies (HttpOnly session cookie is never readable by JS)
 *  - CSRF token read from the non-HttpOnly cookie and sent on every state-changing request
 *  - RFC 9457 problem+json errors surfaced as ApiError
 */
export interface Violation { code: string; severity: string; message: string; keys: string[] }

export class ApiError extends Error {
  status: number;
  code: string;
  errors: { field: string; message: string }[];
  violations: Violation[];
  body: Record<string, unknown>;
  constructor(status: number, body: Record<string, unknown>) {
    super(String(body.detail ?? "Something went wrong"));
    this.status = status;
    this.code = String(body.code ?? "error");
    this.errors = (body.errors as ApiError["errors"]) ?? [];
    this.violations = (body.violations as Violation[]) ?? [];
    this.body = body;
  }
}

const BASE = "/api/v1";
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function csrfToken(): string {
  const m = document.cookie.match(/(?:^|;\s*)nfsu_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (UNSAFE.has(method)) headers["X-CSRF-Token"] = csrfToken();
  const res = await fetch(BASE + path, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  const data = ct.includes("json") ? await res.json() : await res.text();
  if (!res.ok) {
    if (res.status === 401 && onUnauthorized && !path.startsWith("/auth/")) onUnauthorized();
    throw new ApiError(res.status, typeof data === "object" && data ? data : { detail: String(data) });
  }
  return data as T;
}

export const api = {
  get: <T>(p: string) => request<T>("GET", p),
  post: <T>(p: string, b?: unknown) => request<T>("POST", p, b ?? {}),
  put: <T>(p: string, b?: unknown) => request<T>("PUT", p, b ?? {}),
  patch: <T>(p: string, b?: unknown) => request<T>("PATCH", p, b ?? {}),
  del: <T = void>(p: string) => request<T>("DELETE", p),
};

/** Build a query string, dropping empty values. */
export function qs(params: Record<string, string | number | boolean | undefined | null | (string | number)[]>) {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => u.append(k, String(x)));
    else u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

/** Download a file from the API (exports) using the browser's own download flow. */
export function downloadUrl(path: string) {
  const a = document.createElement("a");
  a.href = BASE + path;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}
