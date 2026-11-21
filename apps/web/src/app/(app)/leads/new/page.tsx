"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { apiJson, QueuedError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { nextActionPresets } from "@/lib/dates";
import type { Lead, QuickAddBody, Source } from "@/lib/types";

const SOURCES: Source[] = ["facebook", "walk_in", "referral", "oem", "other"];

export default function QuickAdd() {
  const t = useTranslations("quickAdd");
  const sourceT = useTranslations("source");
  const presetT = useTranslations("nextActionPreset");
  const common = useTranslations("common");
  const router = useRouter();
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [model, setModel] = useState("");
  const [source, setSource] = useState<Source>("walk_in");
  const presets = nextActionPresets();
  const PRESET_KEYS = ["today6pm", "tomorrow10am", "in3Days", "nextWeek"] as const;
  const [nextAt, setNextAt] = useState<string>(presets[0].value());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      const body: QuickAddBody = {
        name,
        phone,
        source,
        model_interest: model || null,
        next_action_at: nextAt,
      };
      const lead = await apiJson.post<Lead>("/v1/leads", body);
      router.replace(`/leads/${lead.id}`);
    } catch (e) {
      if (e instanceof QueuedError) {
        router.replace("/leads");
        return;
      }
      setError(e instanceof Error ? e.message : common("save"));
    } finally {
      setBusy(false);
    }
  }

  const ready = phone.replace(/\D/g, "").length >= 10 && name.trim().length > 0;

  return (
    <>
      <h1 className="mb-3 text-xl font-semibold">{t("title")}</h1>
      <Card className="space-y-4">
        <div className="space-y-1">
          <label className="text-xs text-muted">{t("phone")}</label>
          <Input
            inputMode="numeric"
            placeholder="98765 43210"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            autoFocus
            data-testid="qa-phone"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted">{t("name")}</label>
          <Input value={name} onChange={(e) => setName(e.target.value)} data-testid="qa-name" />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted">{t("model")}</label>
          <Input value={model} onChange={(e) => setModel(e.target.value)} />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted">{t("source")}</label>
          <div className="flex flex-wrap gap-2">
            {SOURCES.map((s) => (
              <button
                key={s}
                onClick={() => setSource(s)}
                type="button"
                className={cn(
                  "rounded-full border px-3 py-1 text-xs",
                  source === s ? "border-primary bg-primary/10 text-primary" : "border-border text-muted",
                )}
              >
                {sourceT(s)}
              </button>
            ))}
          </div>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted">{t("nextAction")}</label>
          <div className="flex flex-wrap gap-2">
            {presets.map((p, i) => {
              const iso = p.value();
              const active = iso === nextAt;
              return (
                <button
                  key={PRESET_KEYS[i]}
                  onClick={() => setNextAt(iso)}
                  type="button"
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs",
                    active ? "border-primary bg-primary/10 text-primary" : "border-border text-muted",
                  )}
                >
                  {presetT(PRESET_KEYS[i])}
                </button>
              );
            })}
          </div>
        </div>
        {error && <p className="text-sm text-danger">{error}</p>}
        <Button onClick={submit} disabled={!ready || busy} className="w-full" size="lg" data-testid="qa-submit">
          {busy ? t("adding") : t("add")}
        </Button>
      </Card>
    </>
  );
}
