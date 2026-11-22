"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { MapPin } from "lucide-react";
import { Card } from "@/components/ui/card";
import { apiJson } from "@/lib/api";
import { useLocaleCtx } from "@/lib/i18n/provider";
import { uiLocaleFor } from "@/lib/languages";
import type { FarmerMe, NearbyTehsil } from "@/lib/types";

export default function FarmHome() {
  const t = useTranslations("farm");
  const common = useTranslations("common");
  const { locale, setLocale } = useLocaleCtx();
  const [me, setMe] = useState<FarmerMe | null>(null);
  const [nearby, setNearby] = useState<NearbyTehsil[]>([]);

  useEffect(() => {
    apiJson.get<FarmerMe>("/v1/farmer/me").then((m) => {
      setMe(m);
      const ui = uiLocaleFor(m.language);
      if (ui !== locale) setLocale(ui);
      apiJson
        .get<NearbyTehsil[]>(`/v1/locations/tehsils/${m.tehsil.id}/nearby?lang=${m.language}`)
        .then(setNearby);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!me) return <p className="text-muted">{common("loading")}</p>;

  const around = nearby.filter((n) => n.rank > 0);
  const place = [me.village?.name, me.tehsil.name, me.district.name, me.state.name]
    .filter(Boolean)
    .join(", ");

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">{t("greeting", { name: me.display_name })}</h1>
      <Card className="space-y-2">
        <p className="flex items-center gap-2 text-sm">
          <MapPin className="h-4 w-4 text-primary" />
          {place}
        </p>
        {around.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs text-muted">
              {around[0].rank === 99 ? t("sameDistrict") : t("nearbyTehsils")}
            </p>
            <div className="flex flex-wrap gap-2">
              {around.map((n) => (
                <span key={n.id} className="rounded-full bg-black/5 px-3 py-1 text-xs">
                  {n.name}
                </span>
              ))}
            </div>
          </div>
        )}
      </Card>
      <Card>
        <p className="font-medium">{t("comingTitle")}</p>
        <p className="text-sm text-muted">{t("comingBody")}</p>
      </Card>
    </div>
  );
}
