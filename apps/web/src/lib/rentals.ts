// Mirrors apps/api/app/schemas/rental.py.

export const KINDS = [
  "tractor", "rotavator", "cultivator", "plough", "seed_drill", "harvester",
  "sprayer", "thresher", "trolley", "baler", "other",
] as const;
export type Kind = (typeof KINDS)[number];
export type RateUnit = "hour" | "day" | "acre";

export interface Listing {
  id: string;
  owner_farmer_id: string;
  owner_name: string;
  tehsil_id: number;
  tehsil_name: string;
  distance_rank: number | null;
  kind: Kind;
  title: string;
  hp: number | null;
  rate_paise: number;
  rate_unit: RateUnit;
  operator_included: boolean;
  fuel_included: boolean;
  notes: string | null;
  status: "active" | "paused" | "removed";
  owner_rating: number | null;
  owner_rating_count: number;
  owner_badges: string[];
}

export interface Need {
  id: string;
  renter_name: string;
  tehsil_name: string;
  distance_rank: number | null;
  kind: Kind;
  acreage: string | null;
  start_date: string;
  end_date: string;
  budget_paise: number | null;
  notes: string | null;
  status: "open" | "matched" | "closed" | "cancelled";
}

export type BookingAction =
  | "agree" | "decline" | "cancel" | "start" | "complete" | "dispute" | "share_contact" | "rate";

export interface Booking {
  id: string;
  listing_id: string;
  listing_title: string;
  kind: Kind;
  my_role: "owner" | "renter";
  owner_name: string;
  renter_name: string;
  start_date: string;
  end_date: string;
  state: string;
  note: string | null;
  owner_completed: boolean;
  renter_completed: boolean;
  i_shared_contact: boolean;
  they_shared_contact: boolean;
  i_rated: boolean;
  dispute_reason: string | null;
  allowed_actions: BookingAction[];
  other_badges: string[];
  created_at: string;
}

export interface BookingEvent {
  from_state: string | null;
  to_state: string;
  action: string;
  by: "owner" | "renter" | "admin";
  note: string | null;
  at: string;
}

export function rupees(paise: number): string {
  return "₹" + (paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

export function fmtDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export function isoDay(offset: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
}
