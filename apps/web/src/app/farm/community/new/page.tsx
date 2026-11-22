"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiJson } from "@/lib/api";
import { POST_KINDS, blockedReason, type Post, type PostKind } from "@/lib/community";
import { cn } from "@/lib/utils";

const UNITS = ["quintal", "kg", "tonne", "dozen", "crate"] as const;

export default function NewPostPage() {
  const t = useTranslations("community");
  const router = useRouter();
  const [kind, setKind] = useState<PostKind>("ask");
  const [body, setBody] = useState("");
  const [crop, setCrop] = useState("");
  const [price, setPrice] = useState("");
  const [unit, setUnit] = useState<(typeof UNITS)[number]>("quintal");
  const [market, setMarket] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inReview, setInReview] = useState(false);

  const isPrice = kind === "price_report";
  const valid = body.trim().length >= 3 && (!isPrice || (crop.trim().length >= 2 && Number(price) > 0));

  async function submit() {
    setBusy(true);
    setError(null);
    const tags = isPrice
      ? { crop: crop.trim(), price_paise: Math.round(Number(price) * 100), unit, market: market.trim() || null }
      : {};
    try {
      const post = await apiJson.post<Post>("/v1/community/posts", { kind, body: body.trim(), tags });
      if (post.status === "in_review") setInReview(true);
      else router.replace("/farm/community");
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "generic";
      const reason = blockedReason(code);
      if (reason) setError(t(`blocked.${["phone_number", "blocked_word"].includes(reason) ? reason : "other"}`));
      else setError(t(code === "too_many_posts" ? "errors.too_many_posts" : "errors.generic"));
    } finally {
      setBusy(false);
    }
  }

  if (inReview) {
    return (
      <Card className="space-y-3">
        <p className="font-medium">{t("inReviewTitle")}</p>
        <p className="text-sm text-muted">{t("inReviewBody")}</p>
        <Button className="w-full" onClick={() => router.replace("/farm/community")}>{t("backToFeed")}</Button>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">{t("newPost")}</h1>
      <div className="flex flex-wrap gap-2">
        {POST_KINDS.map((k) => (
          <button
            key={k}
            onClick={() => setKind(k)}
            className={cn("rounded-full border px-3 py-1 text-sm",
              kind === k ? "border-primary bg-primary/10 text-primary" : "border-border text-muted")}
          >
            {t(`kind.${k}`)}
          </button>
        ))}
      </div>
      {isPrice && (
        <Card className="space-y-2">
          <div className="flex gap-2">
            <Input placeholder={t("crop")} value={crop} onChange={(e) => setCrop(e.target.value)} data-testid="price-crop" />
            <Input inputMode="decimal" placeholder="₹" value={price} onChange={(e) => setPrice(e.target.value.replace(/[^\d.]/g, ""))} className="w-28" data-testid="price-value" />
          </div>
          <div className="flex flex-wrap gap-2">
            {UNITS.map((u) => (
              <button key={u} onClick={() => setUnit(u)}
                className={cn("rounded-full border px-3 py-1 text-sm",
                  unit === u ? "border-primary bg-primary/10 text-primary" : "border-border text-muted")}>
                /{t(`unit.${u}`)}
              </button>
            ))}
          </div>
          <Input placeholder={t("market")} value={market} onChange={(e) => setMarket(e.target.value)} />
        </Card>
      )}
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        maxLength={2000}
        rows={6}
        placeholder={t(`placeholder.${kind}`)}
        className="w-full rounded-xl border border-border bg-surface p-3 text-base outline-none focus:border-primary"
        data-testid="post-body"
      />
      <p className="text-xs text-muted">{t("noPhoneHint")}</p>
      <Button className="w-full" size="lg" disabled={!valid || busy} onClick={submit} data-testid="post-submit">
        {busy ? t("posting") : t("post")}
      </Button>
      {error && <p className="text-sm text-danger" data-testid="post-error">{error}</p>}
    </div>
  );
}
