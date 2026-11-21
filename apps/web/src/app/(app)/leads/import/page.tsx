"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowLeft, Upload } from "lucide-react";
import { authStore } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { Source } from "@/lib/types";

const CANONICAL_FIELDS = [
  "phone",
  "name",
  "model_interest",
  "source",
  "campaign",
  "ad_name",
  "next_action_at",
] as const;
type Field = (typeof CANONICAL_FIELDS)[number];

const AUTO_MATCHES: Record<Field, string[]> = {
  phone: ["phone", "phone_number", "mobile", "contact"],
  name: ["name", "full_name", "customer_name"],
  model_interest: ["model", "model_interest", "product"],
  source: ["source", "lead_source"],
  campaign: ["campaign", "campaign_name"],
  ad_name: ["ad_name", "ad", "adset_name"],
  next_action_at: ["next_action_at", "follow_up_at", "callback_at"],
};

const SOURCES: Source[] = ["facebook", "walk_in", "referral", "oem", "other"];
const POLICIES = ["skip", "update_customer", "create_lead_only"] as const;

interface ImportResult {
  total: number;
  created: number;
  updated: number;
  skipped: number;
  dry_run: boolean;
  errors: { row: number; field: string | null; message: string }[];
}

async function previewCsv(file: File): Promise<{ headers: string[]; rows: string[][] }> {
  const text = await file.text();
  // Lightweight CSV parse for preview only (first ~10 rows). Server side uses proper CSV.
  const lines = text
    .replace(/﻿/, "")
    .split(/\r?\n/)
    .filter((l) => l.length > 0);
  const parse = (l: string) => l.split(",").map((c) => c.replace(/^"|"$/g, ""));
  if (lines.length === 0) return { headers: [], rows: [] };
  return { headers: parse(lines[0]), rows: lines.slice(1, 11).map(parse) };
}

export default function ImportPage() {
  const t = useTranslations("import");
  const common = useTranslations("common");
  const sourceT = useTranslations("source");
  const fileRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [file, setFile] = useState<File | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [preview, setPreview] = useState<string[][]>([]);
  const [mapping, setMapping] = useState<Record<Field, string>>({
    phone: "", name: "", model_interest: "", source: "",
    campaign: "", ad_name: "", next_action_at: "",
  });
  const [defaultSource, setDefaultSource] = useState<Source>("other");
  const [policy, setPolicy] = useState<(typeof POLICIES)[number]>("create_lead_only");
  const [dryRun, setDryRun] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onFile(f: File) {
    setFile(f);
    setResult(null);
    setError(null);
    if (f.name.toLowerCase().endsWith(".csv")) {
      const { headers, rows } = await previewCsv(f);
      setHeaders(headers);
      setPreview(rows);
      const next = { ...mapping };
      for (const field of CANONICAL_FIELDS) {
        const found = headers.find((h) =>
          AUTO_MATCHES[field].some((pat) => h.toLowerCase().trim() === pat),
        );
        next[field] = found || "";
      }
      setMapping(next);
    } else {
      setHeaders([]);
      setPreview([]);
    }
    setStep(2);
  }

  async function submit() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("mapping", JSON.stringify(mapping));
      form.append("default_source", defaultSource);
      form.append("duplicate_policy", policy);
      form.append("dry_run", dryRun ? "true" : "false");
      const token = authStore.access;
      const res = await fetch("/api/backend/v1/leads/import", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      if (!res.ok) {
        const text = await res.text();
        setError(text);
        return;
      }
      const data = (await res.json()) as ImportResult;
      setResult(data);
      setStep(3);
    } finally {
      setBusy(false);
    }
  }

  function downloadErrors() {
    if (!result) return;
    const header = "row,field,message\n";
    const body = result.errors.map((e) => `${e.row},${e.field ?? ""},${e.message}`).join("\n");
    const blob = new Blob([header + body], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `agrodesk-import-errors-${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const ready = mapping.phone && mapping.name;

  return (
    <>
      <Link href="/leads" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-text">
        <ArrowLeft className="h-4 w-4" /> Leads
      </Link>
      <h1 className="mb-3 text-xl font-semibold">{t("title")}</h1>

      <div className="mb-4 flex gap-2 text-xs text-muted">
        <span className={cn(step >= 1 && "text-primary")}>{t("step1")}</span>
        <span>›</span>
        <span className={cn(step >= 2 && "text-primary")}>{t("step2")}</span>
        <span>›</span>
        <span className={cn(step >= 3 && "text-primary")}>{t("step3")}</span>
      </div>

      {step === 1 && (
        <Card>
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className="flex w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border p-10 hover:border-primary"
          >
            <Upload className="h-6 w-6 text-muted" />
            <p className="text-sm">{t("dropLabel")}</p>
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.xlsx,.xlsm"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
          />
          {file && <p className="mt-2 text-xs text-muted">{file.name}</p>}
        </Card>
      )}

      {step === 2 && (
        <Card className="space-y-4">
          {headers.length > 0 ? (
            <div className="space-y-1 text-xs">
              <p className="text-muted">{t("detected")}:</p>
              <p className="font-mono">{headers.join(" · ")}</p>
            </div>
          ) : (
            <p className="text-xs text-muted">XLSX — columns detected server-side.</p>
          )}

          <div className="space-y-2">
            <p className="text-xs text-muted">{t("mapLabel")}</p>
            {CANONICAL_FIELDS.map((f) => (
              <div key={f} className="flex items-center gap-2">
                <label className="w-36 text-sm">{f}</label>
                <Input
                  value={mapping[f]}
                  onChange={(e) => setMapping({ ...mapping, [f]: e.target.value })}
                  placeholder={f === "phone" || f === "name" ? "required" : "optional"}
                  className="h-9"
                />
              </div>
            ))}
            {!ready && <p className="text-xs text-danger">{t("requiredColumns")}</p>}
          </div>

          <div className="space-y-1">
            <p className="text-xs text-muted">{t("defaultSource")}</p>
            <div className="flex flex-wrap gap-2">
              {SOURCES.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setDefaultSource(s)}
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs",
                    defaultSource === s
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border text-muted",
                  )}
                >
                  {sourceT(s)}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-1">
            <p className="text-xs text-muted">{t("duplicatePolicy")}</p>
            <div className="flex flex-col gap-2">
              {POLICIES.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPolicy(p)}
                  className={cn(
                    "rounded-xl border px-3 py-2 text-left text-sm",
                    policy === p ? "border-primary bg-primary/10 text-primary" : "border-border",
                  )}
                >
                  {t(`policy.${p}`)}
                </button>
              ))}
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
            {t("dryRun")}
          </label>

          {error && <p className="text-sm text-danger">{error}</p>}

          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setStep(1)} className="flex-1">
              {t("back")}
            </Button>
            <Button onClick={submit} disabled={!ready || busy} className="flex-1">
              {busy ? t("submitting") : dryRun ? t("preview") : t("submit")}
            </Button>
          </div>
        </Card>
      )}

      {step === 3 && result && (
        <Card className="space-y-3">
          <p className="text-sm font-medium">
            {result.dry_run ? t("preview") : t("result")}
          </p>
          <p className="text-sm">
            {t("resultLine", {
              total: result.total,
              created: result.created,
              updated: result.updated,
              skipped: result.skipped,
              errors: result.errors.length,
            })}
          </p>
          {result.errors.length > 0 && (
            <>
              <ul className="max-h-48 space-y-1 overflow-auto rounded-xl border border-border p-3 text-xs">
                {result.errors.slice(0, 10).map((e, i) => (
                  <li key={i}>
                    row {e.row}
                    {e.field && ` · ${e.field}`} — {e.message}
                  </li>
                ))}
                {result.errors.length > 10 && (
                  <li className="text-muted">+ {result.errors.length - 10} more</li>
                )}
              </ul>
              <Button variant="outline" onClick={downloadErrors} className="w-full">
                {t("downloadErrors")}
              </Button>
            </>
          )}
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => { setStep(1); setResult(null); setFile(null); }} className="flex-1">
              {t("back")}
            </Button>
            {result.dry_run && (
              <Button onClick={() => { setDryRun(false); setStep(2); }} className="flex-1">
                {t("submit")}
              </Button>
            )}
          </div>
        </Card>
      )}
    </>
  );
}
