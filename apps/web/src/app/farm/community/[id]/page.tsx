"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PostCard } from "@/components/post-card";
import { ApiError, apiJson } from "@/lib/api";
import { ago, blockedReason, type PostDetail } from "@/lib/community";

export default function PostPage() {
  const t = useTranslations("community");
  const { id } = useParams<{ id: string }>();
  const [post, setPost] = useState<PostDetail | null>(null);
  const [missing, setMissing] = useState(false);
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    apiJson.get<PostDetail>(`/v1/community/posts/${id}`).then(setPost).catch(() => setMissing(true));
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function send() {
    setBusy(true);
    setError(null);
    try {
      await apiJson.post(`/v1/community/posts/${id}/replies`, { body: reply.trim() });
      setReply("");
      await load();
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "generic";
      const reason = blockedReason(code);
      setError(reason === "phone_number" ? t("blocked.phone_number") : t("errors.generic"));
    } finally {
      setBusy(false);
    }
  }

  if (missing) return <Card><p className="text-sm text-muted">{t("notFound")}</p></Card>;
  if (!post) return null;

  return (
    <div className="space-y-3">
      <PostCard post={post} link={false} onChange={load} />
      <div className="space-y-2">
        {post.replies.map((r) => (
          <Card key={r.id} className="space-y-1 py-3">
            <p className="text-xs text-muted">{r.author_name} · {ago(r.created_at)}</p>
            <p className="whitespace-pre-wrap text-sm">{r.body}</p>
            {r.status !== "published" && <p className="text-xs text-danger">{t(`status.${r.status}`)}</p>}
          </Card>
        ))}
      </div>
      {post.status === "published" && (
        <div className="flex gap-2">
          <Input value={reply} onChange={(e) => setReply(e.target.value)} placeholder={t("replyPlaceholder")} maxLength={1000} data-testid="reply-input" />
          <Button disabled={busy || reply.trim().length < 1} onClick={send} data-testid="reply-send">{t("send")}</Button>
        </div>
      )}
      {error && <p className="text-sm text-danger">{error}</p>}
    </div>
  );
}
