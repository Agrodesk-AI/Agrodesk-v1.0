"use client";

import { useTranslations } from "next-intl";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { fmtDateTime } from "@/lib/dates";
import type { LeadEvent } from "@/lib/types";

export function Timeline({ events }: { events: LeadEvent[] }) {
  const t = useTranslations("eventType");
  const detail = useTranslations("leadDetail");
  const stageT = useTranslations("stage");
  if (events.length === 0) return <p className="text-sm text-muted">{detail("none")}</p>;
  return (
    <ol className="space-y-2" data-testid="timeline">
      {[...events].reverse().map((e) => (
        <li key={e.id}>
          <Card className="p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Badge tone={e.type === "stage_changed" ? "primary" : "default"}>
                  {safeT(t, e.type)}
                </Badge>
                {e.type === "stage_changed" && (
                  <span className="text-xs text-muted">
                    {safeStage(stageT, e.payload.from)} → {safeStage(stageT, e.payload.to)}
                  </span>
                )}
              </div>
              <span className="text-xs text-muted">{fmtDateTime(e.occurred_at)}</span>
            </div>
            {typeof e.payload?.lost_reason === "string" && (
              <p className="mt-1 text-sm">{e.payload.lost_reason}</p>
            )}
            {typeof e.payload?.notes === "string" && (
              <p className="mt-1 text-sm">{e.payload.notes}</p>
            )}
          </Card>
        </li>
      ))}
    </ol>
  );
}

function safeT(fn: (key: string) => string, key: string): string {
  try { return fn(key); } catch { return key; }
}
function safeStage(fn: (key: string) => string, v: unknown): string {
  if (typeof v !== "string") return "?";
  try { return fn(v); } catch { return v; }
}
