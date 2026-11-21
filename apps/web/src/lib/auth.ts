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

export interface Principal {
  user_id: string;
  role: string;
  dealer_id: string | null;
  exp: number;
}

export function decodePrincipal(access: string | null): Principal | null {
  if (!access) return null;
  try {
    const payload = JSON.parse(atob(access.split(".")[1]));
    return {
      user_id: payload.sub,
      role: payload.role,
      dealer_id: payload.dealer_id ?? null,
      exp: payload.exp,
    };
  } catch {
    return null;
  }
}
