"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Sprout, Store } from "lucide-react";
import { apiJson } from "@/lib/api";
import { authStore, decodePrincipal, homeFor } from "@/lib/auth";
import type { Profile, TokenPair } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Lists every profile on this phone and switches between them.
 *  Offers "add farmer profile" when the account has none. */
export function ProfileSwitcher() {
  const t = useTranslations("profiles");
  const router = useRouter();
  const [profiles, setProfiles] = useState<Profile[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const active = decodePrincipal(authStore.access)?.user_id;

  useEffect(() => {
    apiJson.get<Profile[]>("/v1/auth/profiles").then(setProfiles).catch(() => setProfiles([]));
  }, []);

  async function switchTo(id: string) {
    setBusy(id);
    try {
      const tokens = await apiJson.post<TokenPair>("/v1/auth/switch-profile", { profile_id: id });
      authStore.set(tokens);
      router.replace(homeFor(tokens.active_kind));
    } finally {
      setBusy(null);
    }
  }

  if (profiles === null) return null;
  const hasFarmer = profiles.some((p) => p.kind === "farmer");

  return (
    <div className="space-y-2" data-testid="profile-switcher">
      <p className="text-xs text-muted">{t("title")}</p>
      {profiles.map((p) => {
        const Icon = p.kind === "farmer" ? Sprout : Store;
        const isActive = p.id === active;
        return (
          <button
            key={p.id}
            disabled={isActive || busy !== null}
            onClick={() => switchTo(p.id)}
            className={cn(
              "flex w-full items-center gap-3 rounded-xl border px-3 py-2 text-left text-sm",
              isActive ? "border-primary bg-primary/10" : "border-border hover:bg-black/5",
            )}
          >
            <Icon className="h-5 w-5 shrink-0" />
            <span className="flex-1">
              <span className="block font-medium">{p.display_name}</span>
              <span className="block text-xs text-muted">
                {p.kind === "farmer" ? t("farmer") : t("dealer", { role: p.role })}
              </span>
            </span>
            {isActive && <span className="text-xs text-primary">{t("active")}</span>}
          </button>
        );
      })}
      {!hasFarmer && (
        <button
          onClick={() => router.push("/onboarding")}
          className="w-full rounded-xl border border-dashed border-border px-3 py-2 text-sm text-muted hover:bg-black/5"
        >
          + {t("addFarmer")}
        </button>
      )}
    </div>
  );
}
