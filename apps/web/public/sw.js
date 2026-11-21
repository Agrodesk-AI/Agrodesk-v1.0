// Agrodesk service worker. The offline write queue lives in IndexedDB and is
// replayed by the main thread on 'online' + 'visibilitychange'. This worker
// stays minimal: install/activate hooks only; a Background Sync hook is
// registered when the browser supports it.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("sync", (event) => {
  if (event.tag === "agrodesk-replay") {
    event.waitUntil(
      (async () => {
        const clients = await self.clients.matchAll({ type: "window" });
        for (const c of clients) c.postMessage({ type: "replay-queue" });
      })(),
    );
  }
});
