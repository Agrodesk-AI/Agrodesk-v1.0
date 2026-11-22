"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Phone, MessageCircle, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { apiJson } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Timeline } from "@/components/timeline";
import { TransitionSheet } from "@/components/transition-sheet";
import { fmtDateTime, fmtPhone } from "@/lib/dates";
import type { Customer, Lead, LeadEvent } from "@/lib/types";

export default function LeadDetail() {
  const t = useTranslations("leadDetail");
  const sourceT = useTranslations("source");
  const stageT = useTranslations("stage");
  const common = useTranslations("common");
  const { id } = useParams<{ id: string }>();
  const [lead, setLead] = useState<Lead | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [events, setEvents] = useState<LeadEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [transitionOpen, setTransitionOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const l = await apiJson.get<Lead>(`/v1/leads/${id}`);
      setLead(l);
      const [c, ev] = await Promise.all([
        apiJson.get<Customer>(`/v1/customers/${l.customer_id}`),
        apiJson.get<LeadEvent[]>(`/v1/leads/${id}/events`),
      ]);
      setCustomer(c);
      setEvents(ev);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <p className="text-muted">{common("loading")}</p>;
  if (!lead || !customer) return <p className="text-muted">—</p>;

  const phoneHref = `tel:${customer.phone}`;
  const waHref = `https://wa.me/${customer.phone.replace(/\D/g, "")}`;

  return (
    <>
      <Link href="/leads" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-text">
        <ArrowLeft className="h-4 w-4" /> {t("back")}
      </Link>
      <Card className="space-y-2" data-testid="lead-card">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">{customer.name}</h1>
            <p className="text-sm text-muted">{fmtPhone(customer.phone)}</p>
          </div>
          <Badge
            tone={lead.stage === "won" ? "primary" : lead.stage === "lost" ? "dead" : "default"}
            data-testid="lead-stage"
          >
            {stageT(lead.stage)}
          </Badge>
        </div>
        <p className="text-sm"><span className="text-muted">{t("model")}: </span>{lead.model_interest ?? "—"}</p>
        <p className="text-sm"><span className="text-muted">{t("source")}: </span>{sourceT(lead.source)}</p>
        <p className="text-sm"><span className="text-muted">{t("nextAt")}: </span>{fmtDateTime(lead.next_action_at)}</p>
      </Card>

      <h2 className="mt-5 mb-2 text-sm font-semibold uppercase tracking-wide text-muted">{t("timeline")}</h2>
      <Timeline events={events} />

      <div className="fixed inset-x-0 bottom-16 z-30 border-t border-border bg-surface/95 px-4 py-3 backdrop-blur md:static md:mt-6 md:border-0 md:bg-transparent md:p-0">
        <div className="mx-auto flex max-w-5xl items-center gap-2">
          <a href={phoneHref} className="flex-1">
            <Button variant="outline" className="w-full"><Phone className="h-4 w-4" /> {t("call")}</Button>
          </a>
          <a href={waHref} target="_blank" rel="noreferrer" className="flex-1">
            <Button variant="outline" className="w-full"><MessageCircle className="h-4 w-4" /> {t("whatsapp")}</Button>
          </a>
          <Button onClick={() => setTransitionOpen(true)} className="flex-1" data-testid="open-transition">
            {t("moveStage")}
          </Button>
        </div>
      </div>

      {transitionOpen && (
        <TransitionSheet
          lead={lead}
          onDone={() => { setTransitionOpen(false); load(); }}
          onCancel={() => setTransitionOpen(false)}
        />
      )}
    </>
  );
}
