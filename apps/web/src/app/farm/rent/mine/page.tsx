"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiJson } from "@/lib/api";
import { KINDS, fmtDate, rupees, type Kind, type Listing, type Need, type RateUnit } from "@/lib/rentals";
import { cn } from "@/lib/utils";

const UNITS: RateUnit[] = ["hour", "day", "acre"];
const selectCls = "h-12 w-full rounded-xl border border-border bg-surface px-3 text-base";

/** Owner view: my equipment, add a listing, and nearby farmers who need it. */
export default function MyEquipmentPage() {
  const t = useTranslations("rent");
  const [listings, setListings] = useState<Listing[]>([]);
  const [needs, setNeeds] = useState<Need[]>([]);
  const [adding, setAdding] = useState(false);

  const load = () => {
    apiJson.get<Listing[]>("/v1/rentals/listings/mine").then(setListings);
    apiJson.get<Need[]>("/v1/rentals/needs/nearby").then(setNeeds);
  };
  useEffect(load, []);

  async function setStatus(l: Listing, status: Listing["status"]) {
    await apiJson.patch<Listing>(`/v1/rentals/listings/${l.id}`, { status });
    load();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("myEquipment")}</h1>
        {!adding && <Button size="sm" onClick={() => setAdding(true)} data-testid="add-listing">+ {t("addListing")}</Button>}
      </div>

      {adding && <ListingForm onDone={() => { setAdding(false); load(); }} onCancel={() => setAdding(false)} />}

      {listings.map((l) => (
        <Card key={l.id} className="space-y-1">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="font-medium">{l.title}</p>
              <p className="text-xs text-muted">
                {t(`kind.${l.kind}`)} · {rupees(l.rate_paise)}/{t(`unit.${l.rate_unit}`)}
              </p>
            </div>
            <Badge tone={l.status === "active" ? "primary" : "default"}>{t(`listingStatus.${l.status}`)}</Badge>
          </div>
          <div className="flex gap-3 text-xs">
            {l.status === "active" ? (
              <button className="text-muted hover:underline" onClick={() => setStatus(l, "paused")}>{t("pause")}</button>
            ) : (
              <button className="text-primary hover:underline" onClick={() => setStatus(l, "active")}>{t("resume")}</button>
            )}
            <button className="text-muted hover:underline" onClick={() => setStatus(l, "removed")}>{t("remove")}</button>
          </div>
        </Card>
      ))}

      <div className="space-y-2">
        <p className="text-xs text-muted">{t("nearbyNeeds")}</p>
        {needs.length === 0 ? (
          <Card><p className="text-sm text-muted">{t("noNeeds")}</p></Card>
        ) : (
          needs.map((n) => (
            <Card key={n.id} className="space-y-0.5 py-3">
              <p className="font-medium">
                {t(`kind.${n.kind}`)}{n.acreage ? ` · ${n.acreage} ${t("acres")}` : ""}
              </p>
              <p className="text-xs text-muted">
                {n.renter_name} · {n.tehsil_name} · {fmtDate(n.start_date)}–{fmtDate(n.end_date)}
                {n.budget_paise ? ` · ${rupees(n.budget_paise)}` : ""}
              </p>
              {n.notes && <p className="text-sm">{n.notes}</p>}
            </Card>
          ))
        )}
      </div>
    </div>
  );
}

function ListingForm({ onDone, onCancel }: { onDone: () => void; onCancel: () => void }) {
  const t = useTranslations("rent");
  const [kind, setKind] = useState<Kind>("tractor");
  const [title, setTitle] = useState("");
  const [hp, setHp] = useState("");
  const [rate, setRate] = useState("");
  const [unit, setUnit] = useState<RateUnit>("hour");
  const [operator, setOperator] = useState(false);
  const [fuel, setFuel] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await apiJson.post<Listing>("/v1/rentals/listings", {
        kind, title: title.trim(), hp: hp ? Number(hp) : null,
        rate_paise: Math.round(Number(rate) * 100), rate_unit: unit,
        operator_included: operator, fuel_included: fuel,
      });
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? t("errors.generic") : String(e));
    } finally {
      setBusy(false);
    }
  }

  const valid = title.trim().length >= 2 && Number(rate) > 0;

  return (
    <Card className="space-y-3">
      <select className={selectCls} value={kind} onChange={(e) => setKind(e.target.value as Kind)} data-testid="listing-kind">
        {KINDS.map((k) => <option key={k} value={k}>{t(`kind.${k}`)}</option>)}
      </select>
      <Input placeholder={t("titlePlaceholder")} value={title} onChange={(e) => setTitle(e.target.value)} data-testid="listing-title" />
      <div className="flex gap-2">
        <Input inputMode="numeric" placeholder="HP" value={hp} onChange={(e) => setHp(e.target.value.replace(/\D/g, ""))} className="w-24" />
        <Input inputMode="decimal" placeholder={t("ratePlaceholder")} value={rate} onChange={(e) => setRate(e.target.value.replace(/[^\d.]/g, ""))} data-testid="listing-rate" />
      </div>
      <div className="flex gap-2">
        {UNITS.map((u) => (
          <button
            key={u}
            type="button"
            onClick={() => setUnit(u)}
            className={cn("rounded-full border px-3 py-1 text-sm",
              unit === u ? "border-primary bg-primary/10 text-primary" : "border-border text-muted")}
          >
            /{t(`unit.${u}`)}
          </button>
        ))}
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={operator} onChange={(e) => setOperator(e.target.checked)} className="h-5 w-5" />
        {t("withOperator")}
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={fuel} onChange={(e) => setFuel(e.target.checked)} className="h-5 w-5" />
        {t("withFuel")}
      </label>
      <div className="flex gap-2">
        <Button variant="outline" className="flex-1" onClick={onCancel}>{t("cancel")}</Button>
        <Button className="flex-1" disabled={!valid || busy} onClick={submit} data-testid="listing-save">{t("save")}</Button>
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}
    </Card>
  );
}
