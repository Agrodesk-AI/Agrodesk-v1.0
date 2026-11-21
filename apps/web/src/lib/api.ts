"use client";

import { authStore } from "./auth";
import { enqueue, isQueueable, QueuedError } from "./offline-queue";

const BASE = process.env.NEXT_PUBLIC_API_BASE || "/api/backend";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message?: string) {
    super(message ?? code);
  }
}

/** Plain fetch with Bearer auth — used by the queue replay so we don't re-queue on replay. */
export async function apiRaw(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const token = authStore.access;
  if (token && !headers.has("Authorization")) headers.set("Authorization", `Bearer ${token}`);
  return fetch(input, { ...init, headers });
}

async function refresh(): Promise<boolean> {
  const r = authStore.refresh;
  if (!r) return false;
  try {
    const res = await fetch(`${BASE}/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: r }),
    });
    if (!res.ok) {
      authStore.clear();
      return false;
    }
    authStore.set(await res.json());
    return true;
  } catch {
    return false;
  }
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  const body = typeof init.body === "string" ? init.body : undefined;
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = authStore.access;
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...init, headers });
  } catch (e) {
    if (isQueueable(method, path) && body !== undefined) {
      const headerObj: Record<string, string> = {};
      headers.forEach((v, k) => (headerObj[k] = v));
      const row = await enqueue({ url: `${BASE}${path}`, method, body, headers: headerObj });
      throw new QueuedError(row.id);
    }
    throw e;
  }

  if (res.status === 401 && retry) {
    if (await refresh()) return api<T>(path, init, false);
  }
  if (!res.ok) {
    const text = await res.text();
    let code = "error";
    try {
      const j = JSON.parse(text);
      code = typeof j.detail === "string" ? j.detail : (j.detail?.code ?? "error");
    } catch {
      // ignore
    }
    throw new ApiError(res.status, code, text);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const apiJson = {
  get: <T>(p: string) => api<T>(p, { method: "GET" }),
  post: <T>(p: string, body: unknown) => api<T>(p, { method: "POST", body: JSON.stringify(body) }),
  patch: <T>(p: string, body: unknown) =>
    api<T>(p, { method: "PATCH", body: JSON.stringify(body) }),
  del: <T>(p: string) => api<T>(p, { method: "DELETE" }),
};

export { QueuedError };
