/**
 * Typed fetch wrapper for the Operon API (same-origin, proxied by Next.js).
 * - Echoes the CSRF cookie in X-CSRF-Token on state-changing requests (ADR 0001).
 * - Sends the active organisation in X-Operon-Organisation (ADR 0004); the API verifies membership.
 */
import { getActiveOrganisationId } from "@/features/session/active-organisation";

export class ApiRequestError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId: string | null,
    readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

interface ErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    request_id?: string | null;
    details?: Record<string, unknown>;
  };
}

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

async function ensureCsrfCookie(): Promise<string | null> {
  let token = readCookie("operon_csrf");
  if (!token) {
    // Any API response sets the cookie; the session endpoint is the cheapest.
    await fetch("/api/v1/auth/session", { credentials: "same-origin" }).catch(() => null);
    token = readCookie("operon_csrf");
  }
  return token;
}

export interface RequestOptions {
  body?: unknown;
  /** Multipart form data (file uploads). The browser sets the boundary header. */
  form?: FormData;
  /** Send the active organisation header (default true). */
  tenant?: boolean;
  /** Return the body as text (e.g. CSV) instead of parsing JSON. */
  text?: boolean;
  signal?: AbortSignal;
}

export async function apiRequest<T = unknown>(
  method: string,
  path: string,
  { body, form, tenant = true, signal, text = false }: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (UNSAFE.has(method)) {
    const csrf = await ensureCsrfCookie();
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }
  const org = tenant ? getActiveOrganisationId() : null;
  if (org) headers["X-Operon-Organisation"] = org;

  let response: Response;
  try {
    response = await fetch(path.startsWith("/api/") ? path : `/api/v1${path}`, {
      method,
      headers,
      body: form ?? (body === undefined ? undefined : JSON.stringify(body)),
      credentials: "same-origin",
      signal,
    });
  } catch {
    throw new ApiRequestError(0, "network_error", "The Operon API could not be reached.", null);
  }
  if (response.status === 204) return undefined as T;
  if (text && response.ok) return (await response.text()) as T;
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const envelope = (payload ?? {}) as ErrorEnvelope;
    throw new ApiRequestError(
      response.status,
      envelope.error?.code ?? "http_error",
      envelope.error?.message ?? `Request failed with status ${response.status}.`,
      envelope.error?.request_id ?? response.headers.get("x-request-id"),
      envelope.error?.details ?? {},
    );
  }
  return payload as T;
}

export const api = {
  get: <T>(path: string, opts?: RequestOptions) => apiRequest<T>("GET", path, opts),
  post: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    apiRequest<T>("POST", path, { ...opts, body }),
  put: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    apiRequest<T>("PUT", path, { ...opts, body }),
  patch: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    apiRequest<T>("PATCH", path, { ...opts, body }),
  delete: <T>(path: string, opts?: RequestOptions) => apiRequest<T>("DELETE", path, opts),
};

export function errorMessage(error: unknown): string {
  return error instanceof ApiRequestError ? error.message : "Something went wrong. Try again.";
}
