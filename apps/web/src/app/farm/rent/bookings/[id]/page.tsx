"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { MessageCircle, Phone, Star } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiJson } from "@/lib/api";
import { fmtDateTime } from "@/lib/dates";
import { fmtDate, type Booking, type BookingAction, type BookingEvent } from "@/lib/rentals";
import { cn } from "@/lib/utils";

const STATE_ACTIONS: BookingAction[] = ["agree", "start", "complete", "decline", "cancel", "dispute"];

export default function BookingPage() {
  const t = useTranslations("rent");
  const { id } = useParams<{ id: string }>();
  const [b, setB] = useState<Booking | null>(null);
  const [events, setEvents] = useState<BookingEvent[]>([]);
  const [contact, setContact] = useState<{ name: string; phone: string } | null>(null);
  const [disputeText, setDisputeText] = useState("");
  const [score, setScore] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const booking = await apiJson.get<Booking>(`/v1/rentals/bookings/${id}`);
    setB(booking);
    setEvents(await apiJson.get<BookingEvent[]>(`/v1/rentals/bookings/${id}/events`));
    if (booking.i_shared_contact && booking.they_shared_contact) {
      setContact(await apiJson.get(`/v1/rentals/bookings/${id}/contact`));
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "generic";
      setError(code === "dates_taken" ? t("errors.dates_taken") : t("errors.generic"));
    } finally {
      setBusy(false);
    }
  }

  if (!b) return null;
  const other = b.my_role === "owner" ? b.renter_name : b.owner_name;
  const digits = contact?.phone.replace(/\D/g, "") ?? "";

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">{b.listing_title}</h1>
        <p className="text-sm text-muted">
          {b.my_role === "owner" ? t("renter") : t("owner")}: {other} · {fmtDate(b.start_date)}–{fmtDate(b.end_date)}
        </p>
      </div>

      <Card className="space-y-3">
        <div className="flex items-center justify-between">
          <Badge tone="primary">{t(`state.${b.state}`)}</Badge>
          {b.state === "in_progress" && (
            <span className="text-xs text-muted">
              {t("completedBy", {
                owner: b.owner_completed ? "✓" : "–",
                renter: b.renter_completed ? "✓" : "–",
              })}
            </span>
          )}
        </div>
        {b.note && <p className="text-sm">“{b.note}”</p>}
        {b.dispute_reason && <p className="text-sm text-danger">{b.dispute_reason}</p>}

        <div className="flex flex-wrap gap-2">
          {STATE_ACTIONS.filter((a) => b.allowed_actions.includes(a) && a !== "dispute").map((a) => (
            <Button
              key={a}
              size="sm"
              variant={["decline", "cancel"].includes(a) ? "outline" : "primary"}
              disabled={busy}
              onClick={() => run(() => apiJson.post(`/v1/rentals/bookings/${id}/transition`, { action: a }))}
              data-testid={`action-${a}`}
            >
              {t(`action.${a}`)}
            </Button>
          ))}
        </div>

        {b.allowed_actions.includes("dispute") && (
          <div className="flex gap-2">
            <Input placeholder={t("disputePlaceholder")} value={disputeText} onChange={(e) => setDisputeText(e.target.value)} className="h-10" />
            <Button
              size="sm"
              variant="outline"
              disabled={busy || disputeText.trim().length < 3}
              onClick={() => run(() => apiJson.post(`/v1/rentals/bookings/${id}/transition`, { action: "dispute", note: disputeText.trim() }))}
            >
              {t("action.dispute")}
            </Button>
          </div>
        )}
      </Card>

      <Card className="space-y-2">
        <p className="text-sm font-medium">{t("contactTitle")}</p>
        {contact ? (
          <div className="flex items-center justify-between text-sm">
            <span>{contact.name}</span>
            <span className="flex gap-3">
              <a href={`tel:+${digits}`} className="flex items-center gap-1 text-primary"><Phone className="h-4 w-4" />{t("call")}</a>
              <a href={`https://wa.me/${digits}`} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-primary">
                <MessageCircle className="h-4 w-4" />WhatsApp
              </a>
            </span>
          </div>
        ) : b.allowed_actions.includes("share_contact") ? (
          <>
            <p className="text-xs text-muted">{b.they_shared_contact ? t("theyShared") : t("maskedHint")}</p>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => run(() => apiJson.post(`/v1/rentals/bookings/${id}/share-contact`, {}))} data-testid="share-contact">
              {t("shareMyNumber")}
            </Button>
          </>
        ) : (
          <p className="text-xs text-muted">{b.i_shared_contact ? t("waitingForThem") : t("contactLater")}</p>
        )}
      </Card>

      {b.allowed_actions.includes("rate") && (
        <Card className="space-y-2">
          <p className="text-sm font-medium">{t("rateTitle", { name: other })}</p>
          <div className="flex gap-1">
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} onClick={() => setScore(n)} aria-label={`${n}`}>
                <Star className={cn("h-7 w-7", n <= score ? "fill-current text-primary" : "text-muted")} />
              </button>
            ))}
          </div>
          <Button size="sm" disabled={!score || busy} onClick={() => run(() => apiJson.post(`/v1/rentals/bookings/${id}/rating`, { score }))}>
            {t("submitRating")}
          </Button>
        </Card>
      )}

      {error && <p className="text-sm text-danger">{error}</p>}

      <div className="space-y-1">
        <p className="text-xs text-muted">{t("history")}</p>
        {events.map((e, i) => (
          <p key={i} className="text-xs">
            <span className="text-muted">{fmtDateTime(e.at)}</span> · {t(`by.${e.by}`)} · {t(`state.${e.to_state}`)}
            {e.note ? ` — ${e.note}` : ""}
          </p>
        ))}
      </div>
    </div>
  );
}
