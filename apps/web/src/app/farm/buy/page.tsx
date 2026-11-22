"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiJson } from "@/lib/api";
import type { ConsentText, FarmerMe, Interest, Timeline } from "@/lib/types";
import { cn } from "@/lib/utils";

const HP_RANGES: { key: string; min: number | null; max: number | null }[] = [
  { key: "any", min: null, max: null },
  { key: "<30", min: 10, max: 30 },
  { key: "30-40", min: 30, max: 40 },
  { key: "41-50", min: 41, max: 50 },
  { key: "51-60", min: 51, max: 60 },
  { key: "60+", min: 60, max: 150 },
];
const TIMELINES: Timeline[] = ["now", "1_3_months", "3_6_months", "later"];

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1 text-sm",
        on ? "border-primary bg-primary/10 text-primary" : "border-border text-muted",
      )}
    >
      {children}
    </button>
  );
}

export default function BuyPage() {
  const t = useTranslations("buy");
  const router = useRouter();
  const [consent, setConsent] = useState<ConsentText | null>(null);
  const [brand, setBrand] = useState("");
  const [hp, setHp] = useState("any");
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [notes, setNotes] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadConsent() {
    const me = await apiJson.get<FarmerMe>("/v1/farmer/me");
    setConsent(await apiJson.get<ConsentText>(`/v1/farmer/interests/consent-text?lang=${me.language}`));
    setAgreed(false);
  }

  useEffect(() => {
    loadConsent();
  }, []);

  async function submit() {
    if (!consent || !timeline) return;
    setError(null);
    setBusy(true);
    const range = HP_RANGES.find((r) => r.key === hp)!;
    try {
      await apiJson.post<Interest>("/v1/farmer/interests", {
        brand_hint: brand.trim() || null,
        hp_min: range.min,
        hp_max: range.max,
        timeline,
        notes: notes.trim() || null,
        consent_granted: true,
        consent_version: consent.version,
        consent_language: consent.language,
      });
      router.replace("/farm");
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "generic";
      if (code === "stale_consent_text") await loadConsent();
      const known = ["already_open", "too_many_requests", "stale_consent_text"];
      setError(t(`errors.${known.includes(code) ? code : "generic"}`));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">{t("title")}</h1>
      <Card className="space-y-4">
        <div className="space-y-2">
          <p className="text-sm font-medium">{t("brand")}</p>
          <Input value={brand} onChange={(e) => setBrand(e.target.value)} placeholder={t("brandPlaceholder")} />
        </div>
        <div className="space-y-2">
          <p className="text-sm font-medium">{t("hp")}</p>
          <div className="flex flex-wrap gap-2">
            {HP_RANGES.map((r) => (
              <Chip key={r.key} on={hp === r.key} onClick={() => setHp(r.key)}>
                {r.key === "any" ? t("hpAny") : `${r.key} HP`}
              </Chip>
            ))}
          </div>
        </div>
        <div className="space-y-2">
          <p className="text-sm font-medium">{t("when")}</p>
          <div className="flex flex-wrap gap-2">
            {TIMELINES.map((tl) => (
              <Chip key={tl} on={timeline === tl} onClick={() => setTimeline(tl)}>
                {t(`timeline.${tl}`)}
              </Chip>
            ))}
          </div>
        </div>
        <div className="space-y-2">
          <p className="text-sm font-medium">{t("notes")}</p>
          <Input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={1000} />
        </div>
      </Card>

      {consent && (
        <Card className="space-y-3" data-testid="consent-card">
          <p className="text-sm font-medium">{t("consentTitle")}</p>
          <p className="text-sm leading-relaxed" lang={consent.language}>{consent.text}</p>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              className="h-5 w-5"
              data-testid="consent-agree"
            />
            {t("agree")}
          </label>
        </Card>
      )}

      <Button
        onClick={submit}
        disabled={!agreed || !timeline || busy}
        size="lg"
        className="w-full"
        data-testid="buy-submit"
      >
        {busy ? t("sending") : t("submit")}
      </Button>
      {error && <p className="text-sm text-danger">{error}</p>}
    </div>
  );
}
