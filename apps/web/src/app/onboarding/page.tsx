"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { LocationPicker, type LocationValue } from "@/components/location-picker";
import { ApiError, apiJson } from "@/lib/api";
import { authStore, decodePrincipal } from "@/lib/auth";
import { useLocaleCtx } from "@/lib/i18n/provider";
import { FARMER_LANGUAGES, uiLocaleFor } from "@/lib/languages";
import type { TokenPair } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function OnboardingPage() {
  const t = useTranslations("onboarding");
  const router = useRouter();
  const { locale, setLocale } = useLocaleCtx();
  const [ready, setReady] = useState(false);
  const [name, setName] = useState("");
  const [language, setLanguage] = useState<string>(locale);
  const [picked, setPicked] = useState(false);
  // The saved UI locale loads after first render; follow it until the farmer picks.
  useEffect(() => {
    if (!picked) setLanguage(locale);
  }, [locale, picked]);
  const [dob, setDob] = useState("");
  const [loc, setLoc] = useState<LocationValue>({ tehsil_id: null, village_id: null });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const p = decodePrincipal(authStore.access);
    if (!p || p.exp * 1000 < Date.now()) {
      router.replace("/login");
      return;
    }
    if (p.kind === "farmer") {
      router.replace("/farm");
      return;
    }
    setReady(true);
  }, [router]);

  function pickLanguage(code: string) {
    setPicked(true);
    setLanguage(code);
    setLocale(uiLocaleFor(code));
  }

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      const tokens = await apiJson.post<TokenPair>("/v1/farmer/onboard", {
        display_name: name.trim(),
        language,
        tehsil_id: loc.tehsil_id,
        village_id: loc.village_id,
        dob,
      });
      authStore.set(tokens);
      router.replace("/farm");
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "generic";
      const known = ["age_gate", "village_not_in_tehsil", "unknown_tehsil", "already_onboarded"];
      setError(t(`errors.${known.includes(code) ? code : "generic"}`));
    } finally {
      setBusy(false);
    }
  }

  if (!ready) return <div className="flex h-dvh items-center justify-center text-muted">…</div>;

  const valid = name.trim().length > 0 && loc.tehsil_id !== null && /^\d{4}-\d{2}-\d{2}$/.test(dob);

  return (
    <main className="mx-auto w-full max-w-md px-6 py-8">
      <Card className="space-y-5" data-testid="onboarding-card">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold">{t("title")}</h1>
          <p className="text-sm text-muted">{t("subtitle")}</p>
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium">{t("language")}</p>
          <div className="flex flex-wrap gap-2">
            {FARMER_LANGUAGES.map((l) => (
              <button
                key={l.code}
                type="button"
                onClick={() => pickLanguage(l.code)}
                className={cn(
                  "rounded-full border px-3 py-1 text-sm",
                  language === l.code ? "border-primary bg-primary/10 text-primary" : "border-border text-muted",
                )}
              >
                {l.label}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium">{t("name")}</p>
          <Input value={name} onChange={(e) => setName(e.target.value)} data-testid="onb-name" />
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium">{t("location")}</p>
          <LocationPicker lang={language} onChange={setLoc} />
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium">{t("dob")}</p>
          <Input type="date" value={dob} onChange={(e) => setDob(e.target.value)} data-testid="onb-dob" />
          <p className="text-xs text-muted">{t("dobHint")}</p>
        </div>

        <Button onClick={submit} disabled={!valid || busy} size="lg" className="w-full" data-testid="onb-submit">
          {busy ? t("saving") : t("submit")}
        </Button>
        {error && <p className="text-sm text-danger">{error}</p>}
      </Card>
    </main>
  );
}
