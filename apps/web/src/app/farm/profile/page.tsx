"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ProfileSwitcher } from "@/components/profile-switcher";
import { MyTrustCard } from "@/components/trust-badges";
import { apiJson } from "@/lib/api";
import { authStore } from "@/lib/auth";
import { fmtPhone } from "@/lib/dates";
import { useLocaleCtx } from "@/lib/i18n/provider";
import { FARMER_LANGUAGES, uiLocaleFor } from "@/lib/languages";
import type { FarmerMe } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function FarmProfilePage() {
  const t = useTranslations("profile");
  const common = useTranslations("common");
  const router = useRouter();
  const { setLocale } = useLocaleCtx();
  const [me, setMe] = useState<FarmerMe | null>(null);

  useEffect(() => {
    apiJson.get<FarmerMe>("/v1/farmer/me").then(setMe);
  }, []);

  async function changeLanguage(code: string) {
    const updated = await apiJson.patch<FarmerMe>("/v1/farmer/me", { language: code });
    setMe(updated);
    setLocale(uiLocaleFor(code));
  }

  function logout() {
    authStore.clear();
    router.replace("/login");
  }

  if (!me) return <p className="text-muted">{common("loading")}</p>;

  return (
    <>
      <h1 className="mb-3 text-xl font-semibold">{t("title")}</h1>
      <Card className="space-y-4">
        <div>
          <p className="text-lg font-medium">{me.display_name}</p>
          <p className="text-sm text-muted">{fmtPhone(me.phone)}</p>
          <p className="text-sm text-muted">
            {[me.village?.name, me.tehsil.name, me.district.name, me.state.name].filter(Boolean).join(", ")}
          </p>
        </div>
        <div className="space-y-1">
          <p className="text-xs text-muted">{t("language")}</p>
          <div className="flex flex-wrap gap-2">
            {FARMER_LANGUAGES.map((l) => (
              <button
                key={l.code}
                onClick={() => changeLanguage(l.code)}
                className={cn(
                  "rounded-full border px-3 py-1 text-sm",
                  me.language === l.code ? "border-primary bg-primary/10 text-primary" : "border-border text-muted",
                )}
              >
                {l.label}
              </button>
            ))}
          </div>
        </div>
        <MyTrustCard />
        <ProfileSwitcher />
        <Button variant="outline" onClick={logout} className="w-full">{common("signOut")}</Button>
      </Card>
    </>
  );
}
