"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
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
  const [items, setItems] = useState<TaskWithLead[]>([]);
  const [loading, setLoading] = useState(true);
  const [outcomeFor, setOutcomeFor] = useState<Task | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const tasks = await apiJson.get<Task[]>("/v1/tasks/today");
      const enriched = await Promise.all(
        tasks.map(async (t) => {
          if (!t.lead_id) return { task: t, lead: null };
          try {
            const lead = await apiJson.get<Lead>(`/v1/leads/${t.lead_id}`);
            return { task: t, lead };
          } catch {
            return { task: t, lead: null };
          }
        }),
      );
      setItems(enriched);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <p className="text-muted">Loading…</p>;
  if (items.length === 0)
    return (
      <Empty
        title="No tasks today"
        body="New leads or follow-ups will show up here."
        action={
          <Link href="/leads/new">
            <Button>Add a lead</Button>
          </Link>
        }
      />
    );

  return (
    <>
      <h1 className="mb-3 text-xl font-semibold">Today</h1>
      <div className="space-y-3">
        {items.map(({ task, lead }) => (
          <Card key={task.id} className="space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-medium">{lead?.model_interest ?? "Follow up"}</p>
                <p className="text-sm text-muted">Due {fmtTime(task.due_at)}</p>
              </div>
            </div>
            {lead && (
              <div className="flex flex-wrap items-center gap-2">
                <a
                  href={`tel:${lead.customer_id ? "" : ""}`}
                  className="hidden"
                  aria-hidden
                />
                <Link
                  href={`/leads/${lead.id}`}
                  className="text-sm font-medium text-primary hover:underline"
                >
                  Open lead
                </Link>
              </div>
            )}
            <div className="flex items-center gap-2">
              <Button variant="outline" onClick={() => setOutcomeFor(task)} className="flex-1">
                Mark outcome
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
