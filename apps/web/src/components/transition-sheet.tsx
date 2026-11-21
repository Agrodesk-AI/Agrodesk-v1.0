"use client";

import { useMemo, useState } from "react";
import { apiJson } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { nextActionPresets } from "@/lib/dates";
import type { Lead, Stage } from "@/lib/types";

const TRANSITIONS: Record<Stage, Stage[]> = {
  new: ["contacted", "lost"],
  contacted: ["qualified", "lost"],
  qualified: ["visit_planned", "negotiation", "lost"],
  visit_planned: ["negotiation", "qualified", "lost", "won"],
  negotiation: ["won", "lost", "visit_planned"],
  won: [],
  lost: ["new"],
};

export function TransitionSheet({
  lead,
  onDone,
  onCancel,
}: {
  lead: Lead;
  onDone(): void;
  onCancel(): void;
}) {
  const options = useMemo(() => TRANSITIONS[lead.stage] ?? [], [lead.stage]);
  const [target, setTarget] = useState<Stage | null>(null);
  const [reason, setReason] = useState("");
  const presets = nextActionPresets();
  const [nextAt, setNextAt] = useState<string>(presets[1].value());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const needsReason = target === "lost";
  const needsNext = target && !["won", "lost"].includes(target);

  async function submit() {
    if (!target) return;
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { to_stage: target };
      if (needsReason) body.lost_reason = reason || "unspecified";
      if (needsNext) body.next_action_at = nextAt;
      await apiJson.post(`/v1/leads/${lead.id}/transition`, body);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  if (options.length === 0) {
    return (
      <Sheet open onOpenChange={(o) => !o && onCancel()} title="No transitions">
        <p className="text-sm text-muted">This lead is in a terminal stage ({lead.stage}).</p>
      </Sheet>
    );
  }

  return (
    <Sheet open onOpenChange={(o) => !o && onCancel()} title="Move stage">
      <div className="grid grid-cols-2 gap-2">
        {options.map((s) => (
          <button
            key={s}
            onClick={() => setTarget(s)}
            className={cn(
              "rounded-xl border px-3 py-3 text-sm capitalize",
              target === s ? "border-primary bg-primary/10 text-primary" : "border-border",
            )}
          >
            {s.replace("_", " ")}
          </button>
        ))}
      </div>
      {needsReason && (
        <div className="mt-4 space-y-1">
          <label className="text-xs text-muted">Reason for lost</label>
          <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Bought elsewhere" />
        </div>
      )}
      {needsNext && (
        <div className="mt-4 space-y-1">
          <label className="text-xs text-muted">Next action</label>
          <div className="flex flex-wrap gap-2">
            {presets.map((p) => {
              const iso = p.value();
              const active = iso === nextAt;
              return (
                <button
                  key={p.label}
                  onClick={() => setNextAt(iso)}
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs",
                    active ? "border-primary bg-primary/10 text-primary" : "border-border text-muted",
                  )}
                >
                  {p.label}
                </button>
              );
            })}
          </div>
        </div>
      )}
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
      <Button onClick={submit} disabled={!target || busy} className="mt-4 w-full" size="lg">
        {busy ? "Saving…" : "Save"}
      </Button>
    </Sheet>
  );
}
