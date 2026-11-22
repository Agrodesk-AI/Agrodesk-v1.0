// Mirrors apps/api/app/schemas/community.py.

export const POST_KINDS = [
  "ask", "need_equipment", "offer_equipment", "price_report", "scheme_alert", "experience",
] as const;
export type PostKind = (typeof POST_KINDS)[number];
export const TABS = ["all", "ask", "market", "equipment", "alerts", "stories"] as const;
export type Tab = (typeof TABS)[number];
export const REPORT_REASONS = ["spam", "scam", "abuse", "wrong_info", "other"] as const;

export interface PostTags {
  crop?: string;
  equipment?: string;
  price_paise?: number;
  unit?: string;
  market?: string;
}

export interface Post {
  id: string;
  kind: PostKind;
  author_name: string;
  is_mine: boolean;
  tehsil_id: number;
  tehsil_name: string;
  locality: "village" | "tehsil" | "nearby" | "district" | null;
  language: string;
  body: string;
  tags: PostTags;
  status: "published" | "in_review" | "removed" | "archived";
  helpful_count: number | null;
  i_found_helpful: boolean;
  reply_count: number;
  expires_at: string | null;
  created_at: string;
}

export interface Reply {
  id: string;
  author_name: string;
  is_mine: boolean;
  body: string;
  status: string;
  created_at: string;
}

export interface PostDetail extends Post {
  replies: Reply[];
}

export interface Feed {
  items: Post[];
  page: number;
  has_more: boolean;
}

/** "blocked:phone_number" -> "phone_number" */
export function blockedReason(code: string): string | null {
  return code.startsWith("blocked:") ? code.slice(8).split(",")[0] : null;
}

export function ago(iso: string): string {
  const mins = Math.max(1, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 60) return `${mins}m`;
  const h = Math.round(mins / 60);
  if (h < 48) return `${h}h`;
  return `${Math.round(h / 24)}d`;
}
