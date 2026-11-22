"use client";

import { useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { Flag, MessageSquare, ThumbsUp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Sheet } from "@/components/ui/sheet";
import { TrustBadges } from "@/components/trust-badges";
import { apiJson } from "@/lib/api";
import { REPORT_REASONS, ago, type Post } from "@/lib/community";
import { rupees } from "@/lib/rentals";
import { cn } from "@/lib/utils";

export function PostCard({ post, link = true, onChange }: {
  post: Post;
  link?: boolean;
  onChange?: () => void;
}) {
  const t = useTranslations("community");
  const [helpful, setHelpful] = useState(post.i_found_helpful);
  const [reporting, setReporting] = useState(false);
  const [reported, setReported] = useState(false);

  async function toggleHelpful() {
    const next = !helpful;
    setHelpful(next);
    try {
      await (next
        ? apiJson.put(`/v1/community/posts/${post.id}/helpful`, {})
        : apiJson.del(`/v1/community/posts/${post.id}/helpful`));
      onChange?.();
    } catch {
      setHelpful(!next);
    }
  }

  async function report(reason: string) {
    try {
      await apiJson.post("/v1/community/reports", { target_type: "post", target_id: post.id, reason });
    } finally {
      setReported(true);
      setReporting(false);
    }
  }

  const body = (
    <>
      <div className="flex items-center justify-between gap-2 text-xs text-muted">
        <span>
          {post.author_name} <TrustBadges badges={post.author_badges} /> · {post.tehsil_name}
          {post.locality && post.locality !== "village" && post.locality !== "tehsil" ? ` · ${t(`locality.${post.locality}`)}` : ""}
          {" · "}{ago(post.created_at)}
        </span>
        <Badge tone={post.kind === "scheme_alert" ? "hot" : "default"}>{t(`kind.${post.kind}`)}</Badge>
      </div>
      {post.kind === "price_report" && post.tags.price_paise && (
        <p className="text-lg font-semibold">
          {post.tags.crop} · {rupees(post.tags.price_paise)}/{post.tags.unit}
          {post.tags.market && <span className="text-sm font-normal text-muted"> · {post.tags.market}</span>}
        </p>
      )}
      <p className="whitespace-pre-wrap text-sm leading-relaxed" lang={post.language}>{post.body}</p>
      {post.status !== "published" && (
        <p className="text-xs text-danger">{t(`status.${post.status}`)}</p>
      )}
    </>
  );

  return (
    <Card className="space-y-2" data-testid="post-card">
      {link ? <Link href={`/farm/community/${post.id}`} className="block space-y-2">{body}</Link> : body}
      {post.status === "published" && (
        <div className="flex items-center gap-4 text-xs text-muted">
          {!post.is_mine && (
            <button onClick={toggleHelpful} className={cn("flex items-center gap-1", helpful && "text-primary")} data-testid="helpful">
              <ThumbsUp className={cn("h-4 w-4", helpful && "fill-current")} />
              {t("helpful")}{post.helpful_count !== null ? ` · ${post.helpful_count}` : ""}
            </button>
          )}
          <Link href={`/farm/community/${post.id}`} className="flex items-center gap-1">
            <MessageSquare className="h-4 w-4" /> {post.reply_count > 0 ? post.reply_count : t("reply")}
          </Link>
          {!post.is_mine && (
            <button onClick={() => setReporting(true)} disabled={reported} className="ml-auto flex items-center gap-1">
              <Flag className="h-3.5 w-3.5" /> {reported ? t("reported") : t("report")}
            </button>
          )}
        </div>
      )}
      <Sheet open={reporting} onOpenChange={setReporting} title={t("reportTitle")}>
        <div className="space-y-2">
          {REPORT_REASONS.map((r) => (
            <button key={r} onClick={() => report(r)} className="w-full rounded-xl border border-border px-3 py-2 text-left text-sm hover:bg-black/5">
              {t(`reason.${r}`)}
            </button>
          ))}
        </div>
      </Sheet>
    </Card>
  );
}
