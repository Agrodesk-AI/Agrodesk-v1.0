"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { listQueue, onQueueChange, replay } from "@/lib/offline-queue";
import { apiRaw } from "@/lib/api";

export function OfflineIndicator() {
  const t = useTranslations("common");
  const [online, setOnline] = useState(true);
  const [count, setCount] = useState(0);

  useEffect(() => {
    setOnline(navigator.onLine);
    const refresh = async () => setCount((await listQueue()).length);
    refresh();
    const off = onQueueChange(() => void refresh());

    const onOnline = async () => {
      setOnline(true);
      await replay(apiRaw);
      await refresh();
    };
    const onOffline = () => setOnline(false);
    const onVis = async () => {
      if (document.visibilityState === "visible" && navigator.onLine) {
        await replay(apiRaw);
        await refresh();
      }
    };

    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      off();
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  if (online && count === 0) return null;
  const msg = !online ? t("offline") : t("willSync");
  return (
    <div className="fixed left-1/2 top-2 z-50 -translate-x-1/2 rounded-full bg-accent px-3 py-1 text-xs font-medium text-accent-fg shadow">
      {msg}
      {count > 0 && ` · ${count}`}
    </div>
  );
}
