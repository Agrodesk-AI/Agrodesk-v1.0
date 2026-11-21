"use client";

import { NextIntlClientProvider } from "next-intl";
import { createContext, useContext, useEffect, useState } from "react";
import en from "@/messages/en.json";
import hi from "@/messages/hi.json";
import mr from "@/messages/mr.json";

const MESSAGES = { en, mr, hi };
export type Locale = keyof typeof MESSAGES;
export const LOCALES: Locale[] = ["en", "mr", "hi"];
export const LOCALE_LABELS: Record<Locale, string> = {
  en: "English",
  mr: "मराठी",
  hi: "हिन्दी",
};
const STORAGE_KEY = "agrodesk.locale";

const LocaleContext = createContext<{
  locale: Locale;
  setLocale: (l: Locale) => void;
}>({ locale: "en", setLocale: () => {} });

export function useLocaleCtx() {
  return useContext(LocaleContext);
}

function detectBrowserLocale(): Locale {
  if (typeof navigator === "undefined") return "en";
  for (const lang of navigator.languages ?? [navigator.language]) {
    const base = (lang || "").slice(0, 2).toLowerCase() as Locale;
    if (LOCALES.includes(base)) return base;
  }
  return "en";
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("en");

  useEffect(() => {
    const saved = (typeof window !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null) as
      | Locale
      | null;
    if (saved && LOCALES.includes(saved)) {
      setLocaleState(saved);
    } else {
      setLocaleState(detectBrowserLocale());
    }
  }, []);

  const setLocale = (l: Locale) => {
    if (typeof window !== "undefined") localStorage.setItem(STORAGE_KEY, l);
    setLocaleState(l);
  };

  return (
    <LocaleContext.Provider value={{ locale, setLocale }}>
      <NextIntlClientProvider
        locale={locale}
        messages={MESSAGES[locale]}
        timeZone="Asia/Kolkata"
      >
        {children}
      </NextIntlClientProvider>
    </LocaleContext.Provider>
  );
}
