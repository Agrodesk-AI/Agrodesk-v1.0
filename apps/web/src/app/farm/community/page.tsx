"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PostCard } from "@/components/post-card";
import { apiJson } from "@/lib/api";
import { TABS, type Feed, type Post, type Tab } from "@/lib/community";
import { cn } from "@/lib/utils";

export default function CommunityPage() {
  const t = useTranslations("community");
  const [tab, setTab] = useState<Tab>("all");
  const [items, setItems] = useState<Post[] | null>(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);

  useEffect(() => {
    let live = true;
    setItems(null);
    setPage(1);
    apiJson.get<Feed>(`/v1/community/feed?tab=${tab}&page=1`).then((f) => {
      if (!live) return;
      setItems(f.items);
      setHasMore(f.has_more);
    });
    return () => {
      live = false;
    };
  }, [tab]);

  async function more() {
    const f = await apiJson.get<Feed>(`/v1/community/feed?tab=${tab}&page=${page + 1}`);
    setItems((cur) => [...(cur ?? []), ...f.items]);
    setPage(page + 1);
    setHasMore(f.has_more);
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("title")}</h1>
        <Link href="/farm/community/new">
          <Button size="sm" data-testid="new-post"><Plus className="h-4 w-4" /> {t("newPost")}</Button>
        </Link>
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {TABS.map((x) => (
          <button
            key={x}
            onClick={() => setTab(x)}
            className={cn(
              "shrink-0 rounded-full border px-3 py-1 text-sm",
              tab === x ? "border-primary bg-primary/10 text-primary" : "border-border text-muted",
            )}
          >
            {t(`tab.${x}`)}
          </button>
        ))}
      </div>
      {items === null ? null : items.length === 0 ? (
        <Card><p className="text-sm text-muted">{t("empty")}</p></Card>
      ) : (
        <div className="space-y-2" data-testid="feed">
          {items.map((p) => <PostCard key={p.id} post={p} />)}
          {hasMore && <Button variant="outline" className="w-full" onClick={more}>{t("more")}</Button>}
        </div>
      )}
    </div>
  );
}
