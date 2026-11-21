import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { fmtDateTime } from "@/lib/dates";
import type { LeadEvent } from "@/lib/types";

const TYPE_LABEL: Record<string, string> = {
  created: "Lead created",
  stage_changed: "Stage changed",
  assigned: "Owner changed",
  next_action_scheduled: "Next action scheduled",
  note: "Note",
  call_made: "Call",
  task_completed: "Task completed",
  opted_out: "Opted out",
};

export function Timeline({ events }: { events: LeadEvent[] }) {
  if (events.length === 0) return <p className="text-sm text-muted">Nothing yet.</p>;
  return (
    <ol className="space-y-2">
      {[...events].reverse().map((e) => (
        <li key={e.id}>
          <Card className="p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Badge tone={e.type === "stage_changed" ? "primary" : "default"}>
                  {TYPE_LABEL[e.type] ?? e.type}
                </Badge>
                {e.type === "stage_changed" && (
                  <span className="text-xs text-muted">
                    {String(e.payload.from ?? "?")} → {String(e.payload.to ?? "?")}
                  </span>
                )}
              </div>
              <span className="text-xs text-muted">{fmtDateTime(e.occurred_at)}</span>
            </div>
            {typeof e.payload?.lost_reason === "string" && (
              <p className="mt-1 text-sm">Reason: {e.payload.lost_reason}</p>
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
