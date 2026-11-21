import { addDays, formatDistanceToNowStrict, startOfDay } from "date-fns";
import { formatInTimeZone } from "date-fns-tz";

const TZ = "Asia/Kolkata";

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return formatInTimeZone(new Date(iso), TZ, "d MMM, h:mm a");
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return formatInTimeZone(new Date(iso), TZ, "h:mm a");
}

export function relative(iso: string | null | undefined): string {
  if (!iso) return "—";
  return formatDistanceToNowStrict(new Date(iso), { addSuffix: true });
}

export function nextActionPresets(): { label: string; value: () => string }[] {
  const now = () => new Date();
  const at = (d: Date, h = 10) => {
    const x = new Date(d);
    x.setHours(h, 0, 0, 0);
    return x.toISOString();
  };
  return [
    { label: "Today 6pm", value: () => { const d = now(); d.setHours(18, 0, 0, 0); return d.toISOString(); } },
    { label: "Tomorrow 10am", value: () => at(addDays(startOfDay(now()), 1)) },
    { label: "In 3 days", value: () => at(addDays(startOfDay(now()), 3)) },
    { label: "Next week", value: () => at(addDays(startOfDay(now()), 7)) },
  ];
}

export function fmtPhone(phone: string): string {
  // E.164 + readable for +91: "+91 98765 43210"
  if (phone.startsWith("+91") && phone.length === 13) {
    return `${phone.slice(0, 3)} ${phone.slice(3, 8)} ${phone.slice(8)}`;
  }
  return phone;
}
