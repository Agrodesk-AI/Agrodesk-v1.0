"use client";

const ACCESS = "agrodesk.access";
const REFRESH = "agrodesk.refresh";

export const authStore = {
  get access() {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(ACCESS);
  },
  get refresh() {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(REFRESH);
  },
  set(tokens: { access_token: string; refresh_token: string }) {
    localStorage.setItem(ACCESS, tokens.access_token);
    localStorage.setItem(REFRESH, tokens.refresh_token);
  },
  clear() {
    localStorage.removeItem(ACCESS);
    localStorage.removeItem(REFRESH);
  },
};

/** staff = dealer owner/staff or platform admin; farmer; account = signed in, no profile yet. */
export type ProfileKind = "staff" | "farmer" | "account";

export interface Principal {
  user_id: string;
  role: string;
  dealer_id: string | null;
  kind: ProfileKind;
  account_id: string | null;
  exp: number;
}

export function decodePrincipal(access: string | null): Principal | null {
  if (!access) return null;
  try {
    const b64 = access.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(b64));
    return {
      user_id: payload.sub,
      role: payload.role,
      dealer_id: payload.dealer_id ?? null,
      kind: (payload.kind as ProfileKind) ?? "staff",
      account_id: payload.acct ?? null,
      exp: payload.exp,
    };
  } catch {
    return null;
  }
}

/** Where each profile kind lands after sign-in or a profile switch. */
export function homeFor(kind: ProfileKind): string {
  if (kind === "farmer") return "/farm";
  if (kind === "account") return "/onboarding";
  return "/today";
}
