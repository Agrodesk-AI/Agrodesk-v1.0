"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { apiJson, QueuedError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import type { Outcome, Task } from "@/lib/types";

const OUTCOMES: Outcome[] = [
  "not_picked", "interested", "visit_planned", "price_issue", "bought_elsewhere", "not_interested",
];

export function OutcomeSheet({
  task, onDone, onCancel,
}: { task: Task; onDone(): void; onCancel(): void }) {
  const t = useTranslations("outcome");
  const common = useTranslations("common");
  const [picked, setPicked] = useState<Outcome | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!picked) return;
    setBusy(true);
    setError(null);
    try {
      await apiJson.post(`/v1/tasks/${task.id}/outcome`, { outcome: picked });
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
            onClick={() => setPicked(o)}
            className={cn(
              "rounded-xl border px-3 py-3 text-sm",
              picked === o ? "border-primary bg-primary/10 text-primary" : "border-border",
            )}
          >
            {t(`options.${o}`)}
          </button>
        ))}
      </div>
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
      <Button onClick={submit} disabled={!picked || busy} className="mt-4 w-full" size="lg">
        {busy ? common("saving") : common("save")}
      </Button>
    </Sheet>
  );
}
