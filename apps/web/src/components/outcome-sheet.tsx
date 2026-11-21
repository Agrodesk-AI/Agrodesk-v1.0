"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { apiJson, QueuedError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { fmtDateTime } from "@/lib/dates";
import type { Outcome, Task } from "@/lib/types";

const OUTCOMES: Outcome[] = [
  "not_picked", "interested", "visit_planned", "price_issue", "bought_elsewhere", "not_interested",
];

interface Suggest { outcome: string; next_action_at: string | null; }

export function OutcomeSheet({
  task, onDone, onCancel,
}: { task: Task; onDone(): void; onCancel(): void }) {
  const t = useTranslations("outcome");
  const common = useTranslations("common");
  const [picked, setPicked] = useState<Outcome | null>(null);
  const [suggested, setSuggested] = useState<Suggest | null>(null);
  const [override, setOverride] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!picked) { setSuggested(null); return; }
    let aborted = false;
    (async () => {
      try {
        const s = await apiJson.get<Suggest>(`/v1/tasks/${task.id}/suggest?outcome=${picked}`);
        if (!aborted) setSuggested(s);
      } catch {
        if (!aborted) setSuggested(null);
      }
    })();
    return () => { aborted = true; };
  }, [picked, task.id]);

  const effectiveNext = useMemo(
    () => override ?? suggested?.next_action_at ?? null,
    [override, suggested],
  );

  async function submit() {
    if (!picked) return;
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { outcome: picked };
      if (effectiveNext) body.next_action_at = effectiveNext;
      await apiJson.post(`/v1/tasks/${task.id}/outcome`, body);
      onDone();
    } catch (e) {
      if (e instanceof QueuedError) { onDone(); return; }
      setError(e instanceof Error ? e.message : "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet open onOpenChange={(o) => !o && onCancel()} title={t("title")}>
      <div className="grid grid-cols-2 gap-2">
        {OUTCOMES.map((o) => (
          <button
            key={o}
            onClick={() => { setPicked(o); setOverride(null); }}
            className={cn(
              "rounded-xl border px-3 py-3 text-sm",
              picked === o ? "border-primary bg-primary/10 text-primary" : "border-border",
            )}
          >
            {t(`options.${o}`)}
          </button>
        ))}
      </div>
      {picked && suggested && suggested.next_action_at && (
        <div className="mt-4 rounded-xl bg-secondary/10 px-3 py-2 text-xs">
          <span className="text-muted">Suggested next: </span>
          <span className="font-medium">{fmtDateTime(suggested.next_action_at)}</span>
        </div>
      )}
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
      <Button onClick={submit} disabled={!picked || busy} className="mt-4 w-full" size="lg">
        {busy ? common("saving") : common("save")}
      </Button>
    </Sheet>
  );
}
