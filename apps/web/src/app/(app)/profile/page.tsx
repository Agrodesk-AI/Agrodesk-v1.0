"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiJson } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { authStore } from "@/lib/auth";
import { fmtPhone } from "@/lib/dates";
import type { Me } from "@/lib/types";

export default function ProfilePage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  useEffect(() => { apiJson.get<Me>("/v1/me").then(setMe); }, []);
  function logout() { authStore.clear(); router.replace("/login"); }
  return (
    <>
      <h1 className="mb-3 text-xl font-semibold">Profile</h1>
      {me ? (
        <Card className="space-y-2">
          <p className="text-lg font-medium">{me.name}</p>
          <p className="text-sm text-muted">{fmtPhone(me.phone)}</p>
          <p className="text-sm"><span className="text-muted">Role: </span>{me.role}</p>
          <Button variant="outline" onClick={logout} className="mt-3 w-full">Sign out</Button>
        </Card>
      ) : (
        <p className="text-muted">Loading…</p>
      )}
    </>
  );
}
