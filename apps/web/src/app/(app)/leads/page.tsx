"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
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
        <h1 className="text-xl font-semibold">Leads</h1>
        <Link href="/leads/new"><Button size="sm">+ Add lead</Button></Link>
      </div>
      <div className="mb-3 flex gap-2 overflow-x-auto pb-2">
        <button
          onClick={() => setStage(null)}
          className={cn(
            "rounded-full border px-3 py-1 text-xs",
            stage === null ? "border-primary bg-primary/10 text-primary" : "border-border text-muted",
          )}
        >
          All
        </button>
        {STAGES.map((s) => (
          <button
            key={s}
            onClick={() => setStage(s)}
            className={cn(
              "whitespace-nowrap rounded-full border px-3 py-1 text-xs capitalize",
              stage === s ? "border-primary bg-primary/10 text-primary" : "border-border text-muted",
            )}
          >
            {s.replace("_", " ")}
          </button>
        ))}
      </div>
      {loading ? (
        <p className="text-muted">Loading…</p>
      ) : leads.length === 0 ? (
        <Empty title="No leads yet" body="Start by adding a lead." />
      ) : (
        <div className="space-y-2">
          {leads.map((l) => (
            <Link key={l.id} href={`/leads/${l.id}`} className="block">
              <Card className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate font-medium">{l.model_interest ?? "No model noted"}</p>
                  <p className="text-xs text-muted">{l.source} · Next: {fmtDateTime(l.next_action_at)}</p>
                </div>
                <div className="flex items-center gap-2">
                  {l.score === "hot" && <Badge tone="hot">Hot</Badge>}
                  {l.score === "warm" && <Badge tone="warm">Warm</Badge>}
                  <Badge tone={l.stage === "won" ? "primary" : l.stage === "lost" ? "dead" : "default"}>
                    {l.stage.replace("_", " ")}
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
