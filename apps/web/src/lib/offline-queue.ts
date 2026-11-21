"use client";

import { openDB, type IDBPDatabase } from "idb";

const DB = "agrodesk-offline";
const STORE = "queued_requests";

export interface QueuedRequest {
  id: string;
  url: string;
  method: string;
  body: string;
  headers: Record<string, string>;
  created_at: number;
  retries: number;
  last_error?: string;
}

let dbPromise: Promise<IDBPDatabase> | null = null;
function db() {
  if (!dbPromise) {
    dbPromise = openDB(DB, 1, {
      upgrade(d) {
        if (!d.objectStoreNames.contains(STORE)) {
          d.createObjectStore(STORE, { keyPath: "id" });
        }
      },
    });
  }
  return dbPromise;
}

export async function enqueue(req: Omit<QueuedRequest, "id" | "created_at" | "retries">) {
  const d = await db();
  const row: QueuedRequest = {
    ...req,
    id: crypto.randomUUID(),
    created_at: Date.now(),
    retries: 0,
  };
  await d.put(STORE, row);
  notify();
  return row;
}

export async function listQueue(): Promise<QueuedRequest[]> {
  const d = await db();
  const rows = (await d.getAll(STORE)) as QueuedRequest[];
  return rows.sort((a, b) => a.created_at - b.created_at);
}

export async function remove(id: string) {
  const d = await db();
  await d.delete(STORE, id);
  notify();
}

export async function replay(fetcher: typeof fetch = fetch): Promise<{ sent: number; left: number }> {
  const rows = await listQueue();
  let sent = 0;
  for (const row of rows) {
    try {
      const res = await fetcher(row.url, {
        method: row.method,
        body: row.body || undefined,
        headers: row.headers,
      });
      if (res.ok) {
        await remove(row.id);
        sent++;
      } else if (res.status >= 400 && res.status < 500 && res.status !== 408 && res.status !== 429) {
        // client error → stop retrying, drop it (user will re-do)
        await remove(row.id);
      } else {
        // transient — leave in queue
        await bumpRetry(row.id, `${res.status}`);
      }
    } catch (e) {
      await bumpRetry(row.id, e instanceof Error ? e.message : "network");
      break; // still offline, don't keep hammering
    }
  }
  const left = (await listQueue()).length;
  return { sent, left };
}

async function bumpRetry(id: string, err: string) {
  const d = await db();
  const row = (await d.get(STORE, id)) as QueuedRequest | undefined;
  if (!row) return;
  row.retries += 1;
  row.last_error = err;
  await d.put(STORE, row);
}

const LISTENERS = new Set<() => void>();
function notify() {
  LISTENERS.forEach((cb) => cb());
}
export function onQueueChange(cb: () => void) {
  LISTENERS.add(cb);
  return () => LISTENERS.delete(cb);
}

/** True for requests that make sense to queue offline: POST writes we can replay without stale reads. */
export function isQueueable(method: string, path: string): boolean {
  if (method !== "POST") return false;
  if (path.endsWith("/v1/leads")) return true;
  if (/\/v1\/tasks\/[0-9a-f-]+\/outcome$/.test(path)) return true;
  return false;
}

export class QueuedError extends Error {
  readonly kind = "queued" as const;
  constructor(public readonly id: string) {
    super("queued_offline");
  }
}
