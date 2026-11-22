import { LOCALES, type Locale } from "@/lib/i18n/provider";

/** Farmer content languages. Mirrors SUPPORTED_LANGUAGES in apps/api/app/schemas/farmer.py.
 *  Labels are in each language's own script so farmers can find theirs. */
export const FARMER_LANGUAGES: { code: string; label: string }[] = [
  { code: "hi", label: "हिन्दी" },
  { code: "mr", label: "मराठी" },
  { code: "gu", label: "ગુજરાતી" },
  { code: "pa", label: "ਪੰਜਾਬੀ" },
  { code: "bn", label: "বাংলা" },
  { code: "as", label: "অসমীয়া" },
  { code: "or", label: "ଓଡ଼ିଆ" },
  { code: "ta", label: "தமிழ்" },
  { code: "te", label: "తెలుగు" },
  { code: "kn", label: "ಕನ್ನಡ" },
  { code: "ml", label: "മലയാളം" },
  { code: "ur", label: "اردو" },
  { code: "en", label: "English" },
];

/** UI catalogs exist for fewer languages than content does. Until a language's
 *  catalog lands, its UI chrome is English, never Hindi: a Tamil or Bengali reader
 *  should not be pushed onto Hindi. Place names still render in their language. */
export function uiLocaleFor(lang: string): Locale {
  return (LOCALES as string[]).includes(lang) ? (lang as Locale) : "en";
}
