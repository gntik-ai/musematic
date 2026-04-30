"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { ArrowLeft, CheckCircle2, Loader2, ShieldCheck } from "lucide-react";

import { BackupCodesDisplay } from "@/app/(main)/settings/security/mfa/_components/BackupCodesDisplay";
import { QRCodeDisplay } from "@/app/(main)/settings/security/mfa/_components/QRCodeDisplay";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { InputOTP } from "@/components/ui/input-otp";
import { Progress } from "@/components/ui/progress";
import {
  useMfaConfirmMutation,
  useMfaEnrollMutation,
} from "@/lib/hooks/use-auth-mutations";
import { toast } from "@/lib/hooks/use-toast";
import { ApiError } from "@/types/api";

type MfaStep = "enable" | "qr" | "confirm" | "backup";

interface MfaEnrollFlowProps {
  onEnrolled: () => void;
}

const STEP_ORDER: MfaStep[] = ["enable", "qr", "confirm", "backup"];

export function MfaEnrollFlow({ onEnrolled }: MfaEnrollFlowProps) {
  const t = useTranslations("security.mfa.enrollFlow");
  const [step, setStep] = useState<MfaStep>("enable");
  const [code, setCode] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const enrollMutation = useMfaEnrollMutation();
  const confirmMutation = useMfaConfirmMutation();
  const inputRef = useRef<HTMLInputElement | null>(null);

  const currentStepNumber = STEP_ORDER.indexOf(step) + 1;
  const progress = (currentStepNumber / STEP_ORDER.length) * 100;
  const enrollment = enrollMutation.data;
  const secret = enrollment?.secret ?? enrollment?.secret_key ?? "";

  useEffect(() => {
    if (step === "confirm") {
      inputRef.current?.focus();
    }
  }, [step]);

  async function beginEnrollment() {
    setErrorMessage(null);
    try {
      const response = await enrollMutation.mutateAsync();
      setRecoveryCodes(response.recovery_codes ?? []);
      setStep("qr");
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : t("errors.enroll"));
    }
  }

  async function confirmEnrollment(value: string) {
    if (value.length < 6 || confirmMutation.isPending) {
      return;
    }

    setErrorMessage(null);
    try {
      const response = await confirmMutation.mutateAsync({ code: value });
      if (response.recovery_codes?.length) {
        setRecoveryCodes(response.recovery_codes);
      }
      setStep("backup");
    } catch (error) {
      setCode("");
      setErrorMessage(error instanceof ApiError ? error.message : t("errors.confirm"));
      inputRef.current?.focus();
    }
  }

  useEffect(() => {
    if (step === "confirm" && code.length === 6) {
      void confirmEnrollment(code);
    }
  }, [code, step]);

  function completeEnrollment() {
    toast({ title: t("successTitle"), variant: "success" });
    onEnrolled();
    setStep("enable");
    setCode("");
    setRecoveryCodes([]);
    enrollMutation.reset();
    confirmMutation.reset();
  }

  return (
    <Card>
      <CardHeader className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldCheck className="h-4 w-4 text-brand-accent" />
            {t("title")}
          </CardTitle>
          <span className="text-sm text-muted-foreground">
            {t("stepCounter", { current: currentStepNumber, total: STEP_ORDER.length })}
          </span>
        </div>
        <Progress aria-label={t("progressAria")} value={progress} />
      </CardHeader>
      <CardContent className="space-y-5">
        {step === "enable" ? (
          <div className="space-y-4">
            <div className="space-y-2">
              <h2 className="text-lg font-semibold">{t("enableTitle")}</h2>
              <p className="text-sm text-muted-foreground">{t("enableDescription")}</p>
            </div>
            {errorMessage ? (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {errorMessage}
              </div>
            ) : null}
            <Button
              type="button"
              disabled={enrollMutation.isPending}
              onClick={() => void beginEnrollment()}
            >
              {enrollMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ShieldCheck className="h-4 w-4" />
              )}
              {enrollMutation.isPending ? t("loading") : t("begin")}
            </Button>
          </div>
        ) : null}

        {step === "qr" && enrollment ? (
          <div className="space-y-4">
            <div className="space-y-2">
              <h2 className="text-lg font-semibold">{t("qrTitle")}</h2>
              <p className="text-sm text-muted-foreground">{t("qrDescription")}</p>
            </div>
            <QRCodeDisplay provisioningUri={enrollment.provisioning_uri} secret={secret} />
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
              <Button type="button" variant="ghost" onClick={() => setStep("enable")}>
                <ArrowLeft className="h-4 w-4" />
                {t("back")}
              </Button>
              <Button type="button" onClick={() => setStep("confirm")}>
                {t("next")}
              </Button>
            </div>
          </div>
        ) : null}

        {step === "confirm" ? (
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              void confirmEnrollment(code);
            }}
          >
            <div className="space-y-2">
              <h2 className="text-lg font-semibold">{t("confirmTitle")}</h2>
              <p className="text-sm text-muted-foreground">{t("confirmDescription")}</p>
            </div>
            <InputOTP
              ref={inputRef}
              aria-label={t("codeAria")}
              inputMode="numeric"
              maxLength={6}
              onChange={setCode}
              placeholder="000000"
              value={code}
            />
            {errorMessage ? (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {errorMessage}
              </div>
            ) : null}
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
              <Button type="button" variant="ghost" onClick={() => setStep("qr")}>
                <ArrowLeft className="h-4 w-4" />
                {t("back")}
              </Button>
              <Button
                type="submit"
                disabled={code.length < 6 || confirmMutation.isPending}
              >
                {confirmMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-4 w-4" />
                )}
                {confirmMutation.isPending ? t("verifying") : t("verify")}
              </Button>
            </div>
          </form>
        ) : null}

        {step === "backup" ? (
          <div className="space-y-4">
            <div className="space-y-2">
              <h2 className="text-lg font-semibold">{t("backupTitle")}</h2>
              <p className="text-sm text-muted-foreground">{t("backupDescription")}</p>
            </div>
            <BackupCodesDisplay codes={recoveryCodes} onDismiss={completeEnrollment} />
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
