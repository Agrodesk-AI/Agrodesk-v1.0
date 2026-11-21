"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiJson } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { nextActionPresets } from "@/lib/dates";
import type { Lead, QuickAddBody, Source } from "@/lib/types";

const SOURCES: Source[] = ["facebook", "walk_in", "referral", "oem", "other"];

export default function QuickAdd() {
  const router = useRouter();
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [model, setModel] = useState("");
  const [source, setSource] = useState<Source>("walk_in");
  const [nextAt, setNextAt] = useState<string>(nextActionPresets()[0].value());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      const body: QuickAddBody = {
        name,
        phone,
        source,
        model_interest: model || null,
        next_action_at: nextAt,
      };
      const lead = await apiJson.post<Lead>("/v1/leads", body);
      router.replace(`/leads/${lead.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create lead");
    } finally {
      setBusy(false);
    }
  }

  const presets = nextActionPresets();
  const ready = phone.replace(/\D/g, "").length >= 10 && name.trim().length > 0;

  return (
    <>
      <h1 className="mb-3 text-xl font-semibold">New lead</h1>
      <Card className="space-y-4">
        <div className="space-y-1">
          <label className="text-xs text-muted">Phone</label>
          <Input
            inputMode="numeric"
            placeholder="98765 43210"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            autoFocus
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted">Name</label>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ramesh Patil" />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted">Model of interest</label>
          <Input value={model} onChange={(e) => setModel(e.target.value)} placeholder="Mahindra 575 DI" />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted">Source</label>
          <div className="flex flex-wrap gap-2">
            {SOURCES.map((s) => (
              <button
                key={s}
                onClick={() => setSource(s)}
                type="button"
                className={cn(
                  "rounded-full border px-3 py-1 text-xs capitalize",
                  source === s ? "border-primary bg-primary/10 text-primary" : "border-border text-muted",
                )}
              >
                {s.replace("_", " ")}
              </button>
            ))}
          </div>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted">Next action</label>
          <div className="flex flex-wrap gap-2">
            {presets.map((p) => {
              const iso = p.value();
              const active = iso === nextAt;
              return (
                <button
                  key={p.label}
                  onClick={() => setNextAt(iso)}
                  type="button"
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
        {error && <p className="text-sm text-danger">{error}</p>}
        <Button onClick={submit} disabled={!ready || busy} className="w-full" size="lg">
          {busy ? "Adding…" : "Add lead"}
        </Button>
      </Card>
    </>
  );
}
