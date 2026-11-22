"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { apiJson } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ProfileSwitcher } from "@/components/profile-switcher";
import { authStore } from "@/lib/auth";
import { fmtPhone } from "@/lib/dates";
import { LOCALES, LOCALE_LABELS, useLocaleCtx, type Locale } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import type { Me } from "@/lib/types";

export default function ProfilePage() {
  const t = useTranslations("profile");
  const common = useTranslations("common");
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const { locale, setLocale } = useLocaleCtx();

  useEffect(() => { apiJson.get<Me>("/v1/me").then(setMe); }, []);
  function logout() { authStore.clear(); router.replace("/login"); }

  return (
    <>
      <h1 className="mb-3 text-xl font-semibold">{t("title")}</h1>
      {me ? (
        <Card className="space-y-3">
          <p className="text-lg font-medium">{me.name}</p>
          <p className="text-sm text-muted">{fmtPhone(me.phone)}</p>
          <p className="text-sm">
            <span className="text-muted">{common("role")}: </span>{me.role}
          </p>
          <div className="space-y-1">
            <p className="text-xs text-muted">{t("language")}</p>
            <div className="flex flex-wrap gap-2">
              {LOCALES.map((l) => (
                <button
                  key={l}
                  onClick={() => setLocale(l as Locale)}
                  className={cn(
                    "rounded-full border px-3 py-1 text-sm",
                    locale === l ? "border-primary bg-primary/10 text-primary" : "border-border text-muted",
                  )}
                >
                  {LOCALE_LABELS[l as Locale]}
                </button>
              ))}
            </div>
          </div>
          <ProfileSwitcher />
          <Button variant="outline" onClick={logout} className="mt-3 w-full">{common("signOut")}</Button>
        </Card>
      ) : (
        <p className="text-muted">{common("loading")}</p>
      )}
    </>
  );
}
