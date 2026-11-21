"use client";

import { useState } from "react";
import { apiJson } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import type { Outcome, Task } from "@/lib/types";

const OUTCOMES: { v: Outcome; label: string }[] = [
  { v: "not_picked", label: "Not picked" },
  { v: "interested", label: "Interested" },
  { v: "visit_planned", label: "Visit planned" },
  { v: "price_issue", label: "Price issue" },
  { v: "bought_elsewhere", label: "Bought elsewhere" },
  { v: "not_interested", label: "Not interested" },
];

export function OutcomeSheet({
  task,
  onDone,
  onCancel,
}: {
  task: Task;
  onDone(): void;
  onCancel(): void;
}) {
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
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet open onOpenChange={(o) => !o && onCancel()} title="Mark outcome">
      <div className="grid grid-cols-2 gap-2">
        {OUTCOMES.map((o) => (
          <button
            key={o.v}
            onClick={() => setPicked(o.v)}
            className={cn(
              "rounded-xl border px-3 py-3 text-sm",
              picked === o.v ? "border-primary bg-primary/10 text-primary" : "border-border",
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
      <Button onClick={submit} disabled={!picked || busy} className="mt-4 w-full" size="lg">
        {busy ? "Saving…" : "Save"}
      </Button>
    </Sheet>
  );
}
