// Mirrors the Pydantic schemas in apps/api/app/schemas/.
// When openapi-typescript lands, regenerate this file instead.

export type Role = "owner" | "sales" | "recovery" | "service" | "platform_admin";
export type Stage =
  | "new"
  | "contacted"
  | "qualified"
  | "visit_planned"
  | "negotiation"
  | "won"
  | "lost";
// agrodesk_guide = routed from a farmer's consented buying interest; never set by hand.
export type Source = "facebook" | "walk_in" | "referral" | "oem" | "other" | "agrodesk_guide";
export type Score = "hot" | "warm" | "dead";
export type TaskStatus = "pending" | "done" | "skipped";
export type Outcome =
  | "not_picked"
  | "interested"
  | "visit_planned"
  | "price_issue"
  | "bought_elsewhere"
  | "not_interested"
  | "other";

export interface Profile {
  id: string;
  kind: "staff" | "farmer";
  role: string;
  dealer_id: string | null;
  display_name: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  active_kind: "staff" | "farmer" | "account";
  active_profile_id: string | null;
  profiles: Profile[];
}

/** A location row. id is the official LGD code. */
export interface Place {
  id: number;
  name: string;
  name_en: string;
}

export interface NearbyTehsil extends Place {
  rank: number; // 0 self, 1.. curated neighbour, 99 same-district fallback
}

export interface FarmerMe {
  id: string;
  display_name: string;
  language: string;
  phone: string;
  status: string;
  state: Place;
  district: Place;
  tehsil: Place;
  village: Place | null;
}

export interface Me {
  id: string;
  dealer_id: string | null;
  name: string;
  phone: string;
  role: Role;
  active: boolean;
}

export interface Customer {
  id: string;
  dealer_id: string;
  name: string;
  phone: string;
  language: string;
  village: string | null;
  farm_size_acres: string | null;
  crop: string | null;
  notes: string | null;
  consent_whatsapp: boolean;
  consent_call: boolean;
  opted_out_at: string | null;
}

export interface Lead {
  id: string;
  dealer_id: string;
  customer_id: string;
  source: Source;
  referrer_customer_id: string | null;
  model_interest: string | null;
  stage: Stage;
  score: Score | null;
  owner_user_id: string | null;
  next_action_at: string | null;
  lost_reason: string | null;
  won_at: string | null;
  campaign: string | null;
  ad_name: string | null;
  created_via: string;
  created_at: string;
}

export interface LeadEvent {
  id: string;
  lead_id: string;
  type: string;
  payload: Record<string, unknown>;
  actor_type: string;
  actor_id: string | null;
  occurred_at: string;
}

export interface Task {
  id: string;
  dealer_id: string;
  lead_id: string | null;
  user_id: string;
  due_at: string;
  type: string;
  status: TaskStatus;
  outcome: string | null;
  completed_at: string | null;
}

export interface QuickAddBody {
  name: string;
  phone: string;
  language?: string;
  source: Source;
  model_interest?: string | null;
  next_action_at: string;
  owner_user_id?: string | null;
  campaign?: string | null;
  ad_name?: string | null;
  score?: Score | null;
}

export type InterestStatus = "routing" | "assigned" | "waitlist" | "cancelled" | "closed";
export type Timeline = "now" | "1_3_months" | "3_6_months" | "later";

export interface Interest {
  id: string;
  status: InterestStatus;
  brand_hint: string | null;
  hp_min: number | null;
  hp_max: number | null;
  timeline: Timeline;
  notes: string | null;
  reroute_count: number;
  dealer_name: string | null;
  dealer_phone: string | null;
  created_at: string;
}

export interface ConsentText {
  version: string;
  language: string;
  text: string;
}
