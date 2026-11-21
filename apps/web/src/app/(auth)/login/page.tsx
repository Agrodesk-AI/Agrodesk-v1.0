"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { authStore } from "@/lib/auth";
import type { TokenPair } from "@/lib/types";

type Step = "phone" | "code";

export default function LoginPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function sendOtp() {
    setError(null);
    setBusy(true);
    try {
      await api("/v1/auth/otp/request", { method: "POST", body: JSON.stringify({ phone }) });
      setStep("code");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to send code");
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    setError(null);
    setBusy(true);
    try {
      const tokens = await api<TokenPair>("/v1/auth/otp/verify", {
        method: "POST",
        body: JSON.stringify({ phone, code }),
      });
      authStore.set(tokens);
      router.replace("/today");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invalid code");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="space-y-4">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold">Agrodesk</h1>
        <p className="text-sm text-muted">Sign in with your phone number</p>
      </div>
      {step === "phone" ? (
        <>
          <Input
            inputMode="numeric"
            placeholder="98765 43210"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            autoFocus
          />
          <Button
            onClick={sendOtp}
            disabled={phone.replace(/\D/g, "").length < 10 || busy}
            className="w-full"
            size="lg"
          >
            {busy ? "Sending…" : "Send code"}
          </Button>
        </>
      ) : (
        <>
          <p className="text-sm text-muted">We sent a 6-digit code to {phone}.</p>
          <Input
            inputMode="numeric"
            maxLength={6}
            placeholder="000000"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            autoFocus
            className="text-center tracking-[0.5em]"
          />
          <Button onClick={verify} disabled={code.length !== 6 || busy} className="w-full" size="lg">
            {busy ? "Verifying…" : "Verify"}
          </Button>
          <button
            type="button"
            onClick={() => { setStep("phone"); setCode(""); setError(null); }}
            className="w-full text-sm text-muted hover:underline"
          >
            Change number
          </button>
        </>
      )}
      {error && <p className="text-sm text-danger">{error}</p>}
    </Card>
  );
}
