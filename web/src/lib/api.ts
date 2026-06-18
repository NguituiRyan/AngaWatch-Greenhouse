/**
 * Tiny fetch wrapper for the AngaWatch REST API.
 *
 * - Base URL comes from `VITE_API_BASE_URL` (default http://localhost:8000),
 *   suffixed with `/api/v1`.
 * - A pluggable token provider attaches the JWT bearer header. The AuthContext
 *   wires `setTokenProvider` so every request picks up the latest access token
 *   without threading it through every call site.
 * - `login()` uses the OAuth2 password *form* flow (username = email).
 */

import { DEMO_MODE, demoRequest } from "@/lib/demo";

const RAW_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
export const API_BASE = `${RAW_BASE.replace(/\/+$/, "")}/api/v1`;

type TokenProvider = () => string | null;

let tokenProvider: TokenProvider = () => null;

/** Register the function used to read the current access token (set by AuthContext). */
export function setTokenProvider(provider: TokenProvider): void {
  tokenProvider = provider;
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

interface RequestOptions {
  method?: string;
  /** JSON body — serialized automatically. */
  body?: unknown;
  /** Pre-encoded form body for OAuth2 endpoints. */
  formBody?: URLSearchParams;
  /** Query string params; null/undefined values are dropped. */
  query?: Record<string, string | number | boolean | null | undefined>;
  /** Skip attaching the bearer token (e.g. login). */
  anonymous?: boolean;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(`${API_BASE}${path}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== null && value !== undefined) {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

async function parseError(res: Response): Promise<ApiError> {
  let detail: unknown = null;
  let message = `Request failed with status ${res.status}`;
  try {
    const data = await res.json();
    detail = data;
    if (data && typeof data === "object" && "detail" in data) {
      const d = (data as { detail: unknown }).detail;
      message = typeof d === "string" ? d : JSON.stringify(d);
    }
  } catch {
    // Non-JSON error body — keep the generic message.
  }
  return new ApiError(res.status, message, detail);
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, formBody, query, anonymous, signal } = options;

  // Demo mode (production builds): serve baked-in fixtures, no network.
  if (DEMO_MODE) {
    return demoRequest<T>(formBody ? "POST" : method, path, body);
  }

  const headers: Record<string, string> = {};
  if (!anonymous) {
    const token = tokenProvider();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  let payload: BodyInit | undefined;
  if (formBody) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    payload = formBody;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  const res = await fetch(buildUrl(path, query), {
    method,
    headers,
    body: payload,
    signal,
  });

  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;

  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  get: <T>(path: string, opts?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...opts, method: "GET" }),
  post: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...opts, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...opts, method: "PATCH", body }),
  delete: <T>(path: string, opts?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...opts, method: "DELETE" }),
  /** OAuth2 password-form login. Returns the access/refresh token pair. */
  loginForm: <T>(path: string, form: URLSearchParams) =>
    request<T>(path, { method: "POST", formBody: form, anonymous: true }),
};
