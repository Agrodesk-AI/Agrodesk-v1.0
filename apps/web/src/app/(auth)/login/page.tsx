"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { authStore } from "@/lib/auth";
import type { TokenPair } from "@/lib/types";

type Step = "phone" | "code";

export default function LoginPage() {
  const t = useTranslations("login");
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
      setError(e instanceof Error ? e.message : t("errors.generic"));
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
      setError(e instanceof Error ? e.message : t("errors.badCode"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="space-y-4" data-testid="login-card">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold">{t("title")}</h1>
        <p className="text-sm text-muted">{t("subtitle")}</p>
      </div>
      {step === "phone" ? (
        <>
          <Input
            inputMode="numeric"
            placeholder={t("phonePlaceholder")}
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            autoFocus
            data-testid="login-phone"
          />
          <Button
            onClick={sendOtp}
            disabled={phone.replace(/\D/g, "").length < 10 || busy}
            className="w-full"
            size="lg"
            data-testid="login-send"
          >
            {busy ? t("sending") : t("sendCode")}
          </Button>
        </>
      ) : (
        <>
          <p className="text-sm text-muted">{t("codeHint", { phone })}</p>
          <Input
            inputMode="numeric"
            maxLength={6}
            placeholder="000000"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            autoFocus
            className="text-center tracking-[0.5em]"
            data-testid="login-code"
          />
          <Button
            onClick={verify}
            disabled={code.length !== 6 || busy}
            className="w-full"
            size="lg"
            data-testid="login-verify"
          >
            {busy ? t("verifying") : t("verify")}
          </Button>
          <button
            type="button"
            onClick={() => {
              setStep("phone");
              setCode("");
              setError(null);
            }}
            className="w-full text-sm text-muted hover:underline"
          >
            {t("changeNumber")}
          </button>
        </>
      )}
      {error && <p className="text-sm text-danger">{error}</p>}
    </Card>
  );
}
