import type { Metadata, Viewport } from "next";
import "./globals.css";
import { I18nProvider } from "@/lib/i18n/provider";
import { OfflineIndicator } from "@/components/offline-indicator";

export const metadata: Metadata = {
  title: "Agrodesk",
  description: "Follow up every lead. Help every farmer.",
  manifest: "/manifest.json",
};

export const viewport: Viewport = {
  themeColor: "#1F4D2B",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <I18nProvider>
          <OfflineIndicator />
          {children}
        </I18nProvider>
        <script
          dangerouslySetInnerHTML={{
            __html:
              "if('serviceWorker' in navigator){window.addEventListener('load',()=>navigator.serviceWorker.register('/sw.js').catch(()=>{}));}",
          }}
        />
      </body>
    </html>
  );
}
