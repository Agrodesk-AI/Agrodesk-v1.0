"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { MessageCircle, Phone, Tractor } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { apiJson } from "@/lib/api";
import type { Interest } from "@/lib/types";

/** Farmer's buying requests + the "Buying a tractor?" entry point. */
export function InterestList() {
  const t = useTranslations("farm");
  const [items, setItems] = useState<Interest[] | null>(null);

  const load = () => apiJson.get<Interest[]>("/v1/farmer/interests").then(setItems);
  useEffect(() => {
    load();
  }, []);

  async function cancel(id: string) {
    await apiJson.post<Interest>(`/v1/farmer/interests/${id}/cancel`, {});
    load();
  }

  const open = (items ?? []).filter((i) => ["routing", "assigned", "waitlist"].includes(i.status));

  return (
    <div className="space-y-3">
      <Link href="/farm/buy" className="block" data-testid="buy-cta">
        <Card className="flex items-center gap-3 border-primary/40 bg-primary/5">
          <Tractor className="h-8 w-8 shrink-0 text-primary" />
          <div>
            <p className="font-medium">{t("buyCta")}</p>
            <p className="text-sm text-muted">{t("buyCtaBody")}</p>
          </div>
        </Card>
      </Link>

      {open.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-muted">{t("myRequests")}</p>
          {open.map((i) => {
            const digits = i.dealer_phone?.replace(/\D/g, "") ?? "";
            return (
              <Card key={i.id} className="space-y-2" data-testid="interest-card">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-medium">
                    {i.brand_hint ?? t("anyBrand")}
                    {(i.hp_min || i.hp_max) && (
                      <span className="text-muted"> · {i.hp_min}–{i.hp_max} HP</span>
                    )}
                  </p>
                  <Badge tone={i.status === "assigned" ? "primary" : "default"}>
                    {t(`status.${i.status}`)}
                  </Badge>
                </div>
                {i.status === "assigned" && i.dealer_name && (
                  <div className="flex items-center justify-between gap-2 text-sm">
                    <span>{i.dealer_name}</span>
                    {digits && (
                      <span className="flex gap-3">
                        <a href={`tel:+${digits}`} className="flex items-center gap-1 text-primary">
                          <Phone className="h-4 w-4" /> {t("call")}
                        </a>
                        <a
                          href={`https://wa.me/${digits}`}
                          target="_blank"
                          rel="noreferrer"
                          className="flex items-center gap-1 text-primary"
                        >
                          <MessageCircle className="h-4 w-4" /> {t("whatsapp")}
                        </a>
                      </span>
                    )}
                  </div>
                )}
                {i.status === "waitlist" && <p className="text-sm text-muted">{t("status.waitlist")}</p>}
                <button
                  onClick={() => cancel(i.id)}
                  className="text-xs text-muted hover:underline"
                  data-testid="interest-cancel"
                >
                  {t("cancel")}
                </button>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
