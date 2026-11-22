"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Home, Tractor, User, type LucideIcon } from "lucide-react";
import { authStore, decodePrincipal, homeFor } from "@/lib/auth";
import { cn } from "@/lib/utils";

const items: { href: string; key: "home" | "rent" | "profile"; Icon: LucideIcon }[] = [
  { href: "/farm", key: "home", Icon: Home },
  { href: "/farm/rent", key: "rent", Icon: Tractor },
  { href: "/farm/profile", key: "profile", Icon: User },
];

/** Farmer-mode shell. Dealer tokens are bounced to their own home. */
export default function FarmLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const t = useTranslations("farmNav");
  const [ok, setOk] = useState(false);

  useEffect(() => {
    const p = decodePrincipal(authStore.access);
    if (!p || p.exp * 1000 < Date.now()) {
      authStore.clear();
      router.replace("/login");
      return;
    }
    if (p.kind !== "farmer") {
      router.replace(homeFor(p.kind));
      return;
    }
    setOk(true);
  }, [router]);

  if (!ok) return <div className="flex h-dvh items-center justify-center text-muted">…</div>;

  return (
    <div className="mx-auto min-h-dvh w-full max-w-md pb-20">
      <main className="px-4 pt-4">{children}</main>
      <nav className="fixed inset-x-0 bottom-0 z-40 flex items-center justify-around border-t border-border bg-surface px-2 py-2">
        {items.map(({ href, key, Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex min-w-14 flex-col items-center gap-0.5 py-1 text-xs",
              pathname === href ? "text-primary" : "text-muted",
            )}
          >
            <Icon className="h-5 w-5" />
            {t(key)}
          </Link>
        ))}
      </nav>
    </div>
  );
}
