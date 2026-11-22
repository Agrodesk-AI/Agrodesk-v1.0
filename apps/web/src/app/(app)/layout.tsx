"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { CheckSquare, List, Plus, User, type LucideIcon } from "lucide-react";
import { authStore, decodePrincipal, homeFor, type Principal } from "@/lib/auth";
import { cn } from "@/lib/utils";

type NavItem = { href: string; key: "today" | "leads" | "add" | "profile"; Icon: LucideIcon; primary?: boolean };

const navItems: NavItem[] = [
  { href: "/today", key: "today", Icon: CheckSquare },
  { href: "/leads", key: "leads", Icon: List },
  { href: "/leads/new", key: "add", Icon: Plus, primary: true },
  { href: "/profile", key: "profile", Icon: User },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const nav = useTranslations("nav");
  const [principal, setPrincipal] = useState<Principal | null | undefined>(undefined);

  useEffect(() => {
    const p = decodePrincipal(authStore.access);
    if (!p || p.exp * 1000 < Date.now()) {
      authStore.clear();
      router.replace("/login");
      return;
    }
    if (p.kind !== "staff") {
      // dealer area is staff-only; farmers / new accounts have their own home
      router.replace(homeFor(p.kind));
      return;
    }
    setPrincipal(p);
  }, [router]);

  if (principal === undefined) {
    return <div className="flex h-dvh items-center justify-center text-muted">…</div>;
  }

  return (
    <div className="mx-auto min-h-dvh w-full max-w-5xl pb-20 md:flex md:gap-6 md:pb-6">
      <aside className="hidden md:block md:w-56 md:py-6">
        <div className="mb-6 px-3 text-lg font-semibold">Agrodesk</div>
        <nav className="space-y-1">
          {navItems.map(({ href, key, Icon }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-xl px-3 py-2 text-sm hover:bg-black/5",
                pathname === href && "bg-primary/10 text-primary",
              )}
            >
              <Icon className="h-5 w-5" /> {nav(key)}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="flex-1 px-4 pt-4 md:px-0 md:pt-6">{children}</main>
      <nav className="fixed inset-x-0 bottom-0 z-40 flex items-center justify-around border-t border-border bg-surface px-2 py-2 md:hidden">
        {navItems.map(({ href, key, Icon, primary }) => {
          const active = pathname === href;
          if (primary) {
            return (
              <Link
                key={href}
                href={href}
                className="-mt-6 flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-fg shadow-lg"
                aria-label={nav(key)}
              >
                <Icon className="h-6 w-6" />
              </Link>
            );
          }
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex min-w-14 flex-col items-center gap-0.5 py-1 text-xs",
                active ? "text-primary" : "text-muted",
              )}
            >
              <Icon className="h-5 w-5" />
              {nav(key)}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
