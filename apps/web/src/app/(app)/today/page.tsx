"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { Phone, MessageCircle } from "lucide-react";
import { apiJson } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Empty } from "@/components/ui/empty";
import { OutcomeSheet } from "@/components/outcome-sheet";
import { fmtTime } from "@/lib/dates";
import type { Lead, Task } from "@/lib/types";

interface TaskWithLead {
  task: Task;
  lead: Lead | null;
}

export default function TodayPage() {
  const t = useTranslations("today");
  const common = useTranslations("common");
  const [items, setItems] = useState<TaskWithLead[]>([]);
  const [loading, setLoading] = useState(true);
  const [outcomeFor, setOutcomeFor] = useState<Task | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const tasks = await apiJson.get<Task[]>("/v1/tasks/today");
      const enriched = await Promise.all(
        tasks.map(async (task) => {
          if (!task.lead_id) return { task, lead: null };
          try {
            const lead = await apiJson.get<Lead>(`/v1/leads/${task.lead_id}`);
            return { task, lead };
          } catch {
            return { task, lead: null };
          }
        }),
      );
      setItems(enriched);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <p className="text-muted">{common("loading")}</p>;
  if (items.length === 0)
    return (
      <Empty
        title={t("empty")}
        body={t("emptyBody")}
        action={
          <Link href="/leads/new">
            <Button>{t("addLead")}</Button>
          </Link>
        }
      />
    );

  return (
    <>
      <h1 className="mb-3 text-xl font-semibold">{t("title")}</h1>
      <div className="space-y-3">
        {items.map(({ task, lead }) => (
          <Card key={task.id} className="space-y-3" data-testid="today-task">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-medium">{lead?.model_interest ?? t("openLead")}</p>
                <p className="text-sm text-muted">{t("due", { time: fmtTime(task.due_at) })}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" onClick={() => setOutcomeFor(task)} className="flex-1">
                {t("markOutcome")}
              </Button>
              {lead && (
                <>
                  <Link href={`/leads/${lead.id}`}>
                    <Button variant="ghost" aria-label="Open">
                      <Phone className="h-4 w-4" />
                    </Button>
                  </Link>
                  <Link href={`/leads/${lead.id}`}>
                    <Button variant="ghost" aria-label="Open">
                      <MessageCircle className="h-4 w-4" />
                    </Button>
                  </Link>
                </>
              )}
            </div>
          </Card>
        ))}
      </div>
      {outcomeFor && (
        <OutcomeSheet
          task={outcomeFor}
          onDone={() => { setOutcomeFor(null); load(); }}
          onCancel={() => setOutcomeFor(null)}
        />
      )}
    </>
  );
}
