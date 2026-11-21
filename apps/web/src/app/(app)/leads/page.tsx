"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { apiJson } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Empty } from "@/components/ui/empty";
import { cn } from "@/lib/utils";
import { fmtDateTime } from "@/lib/dates";
import type { Lead, Stage } from "@/lib/types";

const STAGES: Stage[] = ["new", "contacted", "qualified", "visit_planned", "negotiation", "won", "lost"];

export default function LeadsPage() {
  const t = useTranslations("leads");
  const stageT = useTranslations("stage");
  const scoreT = useTranslations("score");
  const common = useTranslations("common");
  const [stage, setStage] = useState<Stage | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const q = stage ? `?stage=${stage}` : "";
    apiJson
      .get<Lead[]>(`/v1/leads${q}`)
      .then(setLeads)
      .finally(() => setLoading(false));
  }, [stage]);

  return (
    <>
      <div className="mb-3 flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("title")}</h1>
        <div className="flex gap-2">
          <Link href="/leads/import"><Button size="sm" variant="outline">Import</Button></Link>
          <Link href="/leads/new"><Button size="sm">{t("addBtn")}</Button></Link>
        </div>
      </div>
      <div className="mb-3 flex gap-2 overflow-x-auto pb-2" data-testid="stage-filters">
        <button
          onClick={() => setStage(null)}
          className={cn(
            "rounded-full border px-3 py-1 text-xs",
            stage === null ? "border-primary bg-primary/10 text-primary" : "border-border text-muted",
          )}
        >
          {t("filters.all")}
        </button>
        {STAGES.map((s) => (
          <button
            key={s}
            onClick={() => setStage(s)}
            className={cn(
              "whitespace-nowrap rounded-full border px-3 py-1 text-xs",
              stage === s ? "border-primary bg-primary/10 text-primary" : "border-border text-muted",
            )}
          >
            {stageT(s)}
          </button>
        ))}
      </div>
      {loading ? (
        <p className="text-muted">{common("loading")}</p>
      ) : leads.length === 0 ? (
        <Empty title={t("empty")} body={t("emptyBody")} />
      ) : (
        <div className="space-y-2" data-testid="lead-list">
          {leads.map((l) => (
            <Link key={l.id} href={`/leads/${l.id}`} className="block" data-testid="lead-row">
              <Card className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate font-medium">{l.model_interest ?? t("noModel")}</p>
                  <p className="text-xs text-muted">
                    {l.source} · {t("nextAt", { at: fmtDateTime(l.next_action_at) })}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {l.score === "hot" && <Badge tone="hot">{scoreT("hot")}</Badge>}
                  {l.score === "warm" && <Badge tone="warm">{scoreT("warm")}</Badge>}
                  <Badge tone={l.stage === "won" ? "primary" : l.stage === "lost" ? "dead" : "default"}>
                    {stageT(l.stage)}
                  </Badge>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
