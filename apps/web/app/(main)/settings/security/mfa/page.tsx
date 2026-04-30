"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { KeyRound, Loader2, RefreshCw, ShieldCheck, ShieldOff } from "lucide-react";

import { BackupCodesDisplay } from "@/app/(main)/settings/security/mfa/_components/BackupCodesDisplay";
import { DisableMfaDialog } from "@/app/(main)/settings/security/mfa/_components/DisableMfaDialog";
import { MfaEnrollFlow } from "@/app/(main)/settings/security/mfa/_components/MfaEnrollFlow";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { InputOTP } from "@/components/ui/input-otp";
import { Label } from "@/components/ui/label";
import { useMfaRecoveryCodesRegenerateMutation } from "@/lib/hooks/use-auth-mutations";
import { toast } from "@/lib/hooks/use-toast";
import { useAuthStore } from "@/store/auth-store";
import { ApiError } from "@/types/api";

export default function MfaSettingsPage() {
  const t = useTranslations("security.mfa");
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);
  const enrolled = user?.mfaEnrolled ?? false;
  const [disableOpen, setDisableOpen] = useState(false);
  const [regenerateOpen, setRegenerateOpen] = useState(false);
  const [totpCode, setTotpCode] = useState("");
  const [regenerateError, setRegenerateError] = useState<string | null>(null);
  const [regeneratedCodes, setRegeneratedCodes] = useState<string[]>([]);
  const regenerateMutation = useMfaRecoveryCodesRegenerateMutation();

  function updateEnrollmentState(nextEnrolled: boolean) {
    if (user) {
      setUser({ ...user, mfaEnrolled: nextEnrolled });
    }
  }

  async function regenerateBackupCodes() {
    setRegenerateError(null);
    try {
      const response = await regenerateMutation.mutateAsync({ totp_code: totpCode });
      setRegeneratedCodes(response.recovery_codes);
      setTotpCode("");
      toast({ title: t("regenerateDialog.successTitle"), variant: "success" });
    } catch (error) {
      setRegenerateError(
        error instanceof ApiError ? error.message : t("regenerateDialog.error"),
      );
    }
  }

  function closeRegenerateDialog() {
    setRegenerateOpen(false);
    setTotpCode("");
    setRegenerateError(null);
    setRegeneratedCodes([]);
    regenerateMutation.reset();
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <ShieldCheck className="h-6 w-6 text-brand-accent" />
          <div>
            <h1 className="text-2xl font-semibold">{t("title")}</h1>
            <p className="text-sm text-muted-foreground">{t("description")}</p>
          </div>
        </div>
        <Badge variant={enrolled ? "default" : "secondary"}>
          {enrolled ? t("status.active") : t("status.notEnrolled")}
        </Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <KeyRound className="h-4 w-4 text-brand-accent" />
            {t("statusTitle")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            {enrolled ? t("activeDescription") : t("notEnrolledDescription")}
          </p>
          {enrolled ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setRegenerateOpen(true)}
              >
                <RefreshCw className="h-4 w-4" />
                {t("regenerateBackupCodes")}
              </Button>
              <Button
                type="button"
                variant="destructive"
                onClick={() => setDisableOpen(true)}
              >
                <ShieldOff className="h-4 w-4" />
                {t("disable")}
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {!enrolled ? (
        <MfaEnrollFlow onEnrolled={() => updateEnrollmentState(true)} />
      ) : null}

      <Dialog
        open={regenerateOpen}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) {
            closeRegenerateDialog();
            return;
          }
          setRegenerateOpen(true);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("regenerateDialog.title")}</DialogTitle>
            <DialogDescription>{t("regenerateDialog.description")}</DialogDescription>
          </DialogHeader>
          {regeneratedCodes.length > 0 ? (
            <BackupCodesDisplay codes={regeneratedCodes} onDismiss={closeRegenerateDialog} />
          ) : (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="regenerate-mfa-code">{t("regenerateDialog.code")}</Label>
                <InputOTP
                  id="regenerate-mfa-code"
                  aria-label={t("regenerateDialog.codeAria")}
                  inputMode="numeric"
                  maxLength={6}
                  onChange={setTotpCode}
                  placeholder="000000"
                  value={totpCode}
                />
              </div>
              {regenerateError ? (
                <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  {regenerateError}
                </div>
              ) : null}
            </div>
          )}
          {regeneratedCodes.length === 0 ? (
            <DialogFooter>
              <Button type="button" variant="outline" onClick={closeRegenerateDialog}>
                {t("regenerateDialog.cancel")}
              </Button>
              <Button
                type="button"
                disabled={totpCode.length < 6 || regenerateMutation.isPending}
                onClick={() => void regenerateBackupCodes()}
              >
                {regenerateMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
                {regenerateMutation.isPending
                  ? t("regenerateDialog.submitting")
                  : t("regenerateDialog.submit")}
              </Button>
            </DialogFooter>
          ) : null}
        </DialogContent>
      </Dialog>

      <DisableMfaDialog
        open={disableOpen}
        onDisabled={() => updateEnrollmentState(false)}
        onOpenChange={setDisableOpen}
      />
    </div>
  );
}
