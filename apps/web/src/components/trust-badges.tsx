"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { HandHeart, ShieldCheck, type LucideIcon } from "lucide-react";
import { apiJson } from "@/lib/api";

const ICONS: Record<string, LucideIcon> = {
  trusted_renter: ShieldCheck,
  helpful_neighbour: HandHeart,
};

/** Public trust display: badges only, never numbers (design §3.7). */
export function TrustBadges({ badges }: { badges: string[] | undefined }) {
  const t = useTranslations("trust");
  if (!badges?.length) return null;
  return (
    <span className="inline-flex flex-wrap gap-1 align-middle">
      {badges.map((b) => {
        const Icon = ICONS[b] ?? ShieldCheck;
        return (
          <span
            key={b}
            title={t(`badgeHint.${b}`)}
            className="inline-flex items-center gap-0.5 rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary"
            data-testid={`badge-${b}`}
          >
            <Icon className="h-3 w-3" />
            {t(`badge.${b}`)}
          </span>
        );
      })}
    </span>
  );
}

interface MyTrust {
  badges: string[];
  progress: {
    trusted_renter: { completed_rentals: [number, number]; open_disputes: number };
    helpful_neighbour: { helpful_marks: [number, number]; distinct_markers: [number, number] };
  };
  rating_avg: number | null;
  rating_count: number;
}

function Bar({ value, goal }: { value: number; goal: number }) {
  const pct = Math.min(100, Math.round((value / goal) * 100));
  return (
    <div className="h-1.5 w-full rounded-full bg-black/10">
      <div className="h-1.5 rounded-full bg-primary" style={{ width: `${pct}%` }} />
    </div>
  );
}

/** The farmer's own view: badges plus how close they are (numbers only for themself). */
export function MyTrustCard() {
  const t = useTranslations("trust");
  const [me, setMe] = useState<MyTrust | null>(null);
  useEffect(() => {
    apiJson.get<MyTrust>("/v1/farmer/trust").then(setMe).catch(() => setMe(null));
  }, []);
  if (!me) return null;
  const r = me.progress.trusted_renter;
  const h = me.progress.helpful_neighbour;
  return (
    <div className="space-y-3" data-testid="my-trust">
      <p className="text-xs text-muted">{t("title")}</p>
      {me.badges.length ? <TrustBadges badges={me.badges} /> : <p className="text-sm text-muted">{t("none")}</p>}
      {!me.badges.includes("trusted_renter") && (
        <div className="space-y-1">
          <p className="text-sm">{t("badge.trusted_renter")}</p>
          <Bar value={r.completed_rentals[0]} goal={r.completed_rentals[1]} />
          <p className="text-xs text-muted">
            {t("rentalsProgress", { n: r.completed_rentals[0], goal: r.completed_rentals[1] })}
            {r.open_disputes > 0 ? ` · ${t("openDisputes", { n: r.open_disputes })}` : ""}
          </p>
        </div>
      )}
      {!me.badges.includes("helpful_neighbour") && (
        <div className="space-y-1">
          <p className="text-sm">{t("badge.helpful_neighbour")}</p>
          <Bar value={h.helpful_marks[0]} goal={h.helpful_marks[1]} />
          <p className="text-xs text-muted">
            {t("helpfulProgress", {
              n: h.helpful_marks[0], goal: h.helpful_marks[1],
              people: h.distinct_markers[0], peopleGoal: h.distinct_markers[1],
            })}
          </p>
        </div>
      )}
      {me.rating_count > 0 && (
        <p className="text-xs text-muted">{t("myRating", { avg: me.rating_avg ?? 0, n: me.rating_count })}</p>
      )}
    </div>
  );
}
