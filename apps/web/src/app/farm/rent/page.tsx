"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { Star, Wrench } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Sheet } from "@/components/ui/sheet";
import { TrustBadges } from "@/components/trust-badges";
import { ApiError, apiJson } from "@/lib/api";
import {
  KINDS, fmtDate, isoDay, rupees,
  type Booking, type Kind, type Listing,
} from "@/lib/rentals";
import { cn } from "@/lib/utils";

/** Find equipment near me, request it, and see my bookings. */
export default function RentPage() {
  const t = useTranslations("rent");
  const [kind, setKind] = useState<Kind | null>(null);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [listings, setListings] = useState<Listing[] | null>(null);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [picked, setPicked] = useState<Listing | null>(null);
  const [needOpen, setNeedOpen] = useState(false);
  const [needPosted, setNeedPosted] = useState(false);

  useEffect(() => {
    let live = true;
    const q = new URLSearchParams();
    if (kind) q.set("kind", kind);
    if (start && end) {
      q.set("start_date", start);
      q.set("end_date", end);
    }
    apiJson.get<Listing[]>(`/v1/rentals/listings?${q}`).then((r) => live && setListings(r));
    return () => {
      live = false;
    };
  }, [kind, start, end]);

  const loadBookings = () => apiJson.get<Booking[]>("/v1/rentals/bookings").then(setBookings);
  useEffect(() => {
    loadBookings();
  }, []);

  const active = bookings.filter((b) => !["declined", "cancelled", "rated", "resolved"].includes(b.state));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("title")}</h1>
        <Link href="/farm/rent/mine" className="flex items-center gap-1 text-sm text-primary">
          <Wrench className="h-4 w-4" /> {t("myEquipment")}
        </Link>
      </div>

      {active.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-muted">{t("myBookings")}</p>
          {active.map((b) => (
            <Link key={b.id} href={`/farm/rent/bookings/${b.id}`} className="block">
              <Card className="flex items-center justify-between gap-2 py-3">
                <div className="min-w-0">
                  <p className="truncate font-medium">{b.listing_title}</p>
                  <p className="text-xs text-muted">
                    {b.my_role === "owner" ? b.renter_name : b.owner_name} · {fmtDate(b.start_date)}–{fmtDate(b.end_date)}
                  </p>
                </div>
                <Badge tone={b.allowed_actions.some((a) => a !== "share_contact") ? "hot" : "default"}>
                  {t(`state.${b.state}`)}
                </Badge>
              </Card>
            </Link>
          ))}
        </div>
      )}

      <div className="space-y-2">
        <div className="flex gap-2 overflow-x-auto pb-1">
          <Chip on={kind === null} onClick={() => setKind(null)}>{t("allKinds")}</Chip>
          {KINDS.map((k) => (
            <Chip key={k} on={kind === k} onClick={() => setKind(k)}>{t(`kind.${k}`)}</Chip>
          ))}
        </div>
        <div className="flex items-center gap-2 text-sm">
          <Input type="date" min={isoDay(0)} value={start} onChange={(e) => setStart(e.target.value)} className="h-10" />
          <span className="text-muted">–</span>
          <Input type="date" min={start || isoDay(0)} value={end} onChange={(e) => setEnd(e.target.value)} className="h-10" />
        </div>
      </div>

      <Card className="flex items-center justify-between gap-2 py-3">
        <p className="text-sm text-muted">{needPosted ? t("needPosted") : t("postNeedHint")}</p>
        <Button size="sm" variant="outline" onClick={() => setNeedOpen(true)} data-testid="post-need">
          {t("postNeed")}
        </Button>
      </Card>

      {listings === null ? null : listings.length === 0 ? (
        <Card><p className="text-sm text-muted">{t("noListings")}</p></Card>
      ) : (
        <div className="space-y-2" data-testid="listing-list">
          {listings.map((l) => (
            <Card key={l.id} className="space-y-1">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-medium">{l.title}</p>
                  <p className="text-xs text-muted">
                    {t(`kind.${l.kind}`)}{l.hp ? ` · ${l.hp} HP` : ""} · {l.owner_name} · {l.tehsil_name}
                  </p>
                  <TrustBadges badges={l.owner_badges} />
                </div>
                <p className="shrink-0 font-semibold">
                  {rupees(l.rate_paise)}<span className="text-xs font-normal text-muted">/{t(`unit.${l.rate_unit}`)}</span>
                </p>
              </div>
              <div className="flex items-center justify-between gap-2 text-xs text-muted">
                <span className="flex gap-2">
                  {l.operator_included && <span>{t("withOperator")}</span>}
                  {l.fuel_included && <span>{t("withFuel")}</span>}
                  {l.owner_rating !== null && (
                    <span className="flex items-center gap-0.5">
                      <Star className="h-3 w-3 fill-current" /> {l.owner_rating} ({l.owner_rating_count})
                    </span>
                  )}
                </span>
                <Button size="sm" onClick={() => setPicked(l)} data-testid="listing-request">{t("request")}</Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <NeedSheet
        open={needOpen}
        defaultKind={kind ?? "tractor"}
        onClose={() => setNeedOpen(false)}
        onDone={() => {
          setNeedOpen(false);
          setNeedPosted(true);
        }}
      />
      <RequestSheet
        listing={picked}
        defaultStart={start}
        defaultEnd={end}
        onClose={() => setPicked(null)}
        onDone={() => {
          setPicked(null);
          loadBookings();
        }}
      />
    </div>
  );
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "shrink-0 rounded-full border px-3 py-1 text-sm",
        on ? "border-primary bg-primary/10 text-primary" : "border-border text-muted",
      )}
    >
      {children}
    </button>
  );
}

function RequestSheet({
  listing, defaultStart, defaultEnd, onClose, onDone,
}: {
  listing: Listing | null;
  defaultStart: string;
  defaultEnd: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const t = useTranslations("rent");
  const [start, setStart] = useState(defaultStart);
  const [end, setEnd] = useState(defaultEnd);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setStart(defaultStart || isoDay(1));
    setEnd(defaultEnd || defaultStart || isoDay(1));
    setNote("");
    setError(null);
  }, [listing, defaultStart, defaultEnd]);

  async function submit() {
    if (!listing) return;
    setBusy(true);
    setError(null);
    try {
      await apiJson.post<Booking>("/v1/rentals/bookings", {
        listing_id: listing.id, start_date: start, end_date: end, note: note.trim() || null,
      });
      onDone();
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "generic";
      const known = ["dates_taken", "already_requested", "too_far", "too_many_requests", "start_in_past"];
      setError(t(`errors.${known.includes(code) ? code : "generic"}`));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet open={listing !== null} onOpenChange={(o) => !o && onClose()} title={listing?.title ?? ""}>
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Input type="date" min={isoDay(0)} value={start} onChange={(e) => setStart(e.target.value)} />
          <span className="text-muted">–</span>
          <Input type="date" min={start} value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
        <Input placeholder={t("notePlaceholder")} value={note} onChange={(e) => setNote(e.target.value)} />
        <p className="text-xs text-muted">{t("maskedHint")}</p>
        <Button className="w-full" size="lg" disabled={!start || !end || end < start || busy} onClick={submit} data-testid="request-submit">
          {busy ? t("sending") : t("sendRequest")}
        </Button>
        {error && <p className="text-sm text-danger">{error}</p>}
      </div>
    </Sheet>
  );
}

function NeedSheet({
  open, defaultKind, onClose, onDone,
}: {
  open: boolean;
  defaultKind: Kind;
  onClose: () => void;
  onDone: () => void;
}) {
  const t = useTranslations("rent");
  const [kind, setKind] = useState<Kind>(defaultKind);
  const [start, setStart] = useState(isoDay(1));
  const [end, setEnd] = useState(isoDay(1));
  const [acres, setAcres] = useState("");
  const [budget, setBudget] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) setKind(defaultKind);
  }, [open, defaultKind]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await apiJson.post("/v1/rentals/needs", {
        kind, start_date: start, end_date: end,
        acreage: acres ? acres : null,
        budget_paise: budget ? Math.round(Number(budget) * 100) : null,
      });
      onDone();
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "generic";
      setError(t(`errors.${["too_many_requests", "start_in_past"].includes(code) ? code : "generic"}`));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()} title={t("postNeed")}>
      <div className="space-y-3">
        <select
          className="h-12 w-full rounded-xl border border-border bg-surface px-3 text-base"
          value={kind}
          onChange={(e) => setKind(e.target.value as Kind)}
        >
          {KINDS.map((k) => <option key={k} value={k}>{t(`kind.${k}`)}</option>)}
        </select>
        <div className="flex items-center gap-2">
          <Input type="date" min={isoDay(0)} value={start} onChange={(e) => setStart(e.target.value)} />
          <span className="text-muted">–</span>
          <Input type="date" min={start} value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
        <div className="flex gap-2">
          <Input inputMode="decimal" placeholder={t("acres")} value={acres} onChange={(e) => setAcres(e.target.value.replace(/[^\d.]/g, ""))} />
          <Input inputMode="decimal" placeholder={t("budget")} value={budget} onChange={(e) => setBudget(e.target.value.replace(/[^\d.]/g, ""))} />
        </div>
        <p className="text-xs text-muted">{t("needHint")}</p>
        <Button className="w-full" size="lg" disabled={busy || !start || end < start} onClick={submit} data-testid="need-submit">
          {busy ? t("sending") : t("postNeed")}
        </Button>
        {error && <p className="text-sm text-danger">{error}</p>}
      </div>
    </Sheet>
  );
}
