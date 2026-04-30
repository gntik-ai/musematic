"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2, ShieldOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { InputOTP } from "@/components/ui/input-otp";
import { Label } from "@/components/ui/label";
import { useMfaDisableMutation } from "@/lib/hooks/use-auth-mutations";
import { toast } from "@/lib/hooks/use-toast";
import { ApiError } from "@/types/api";

interface DisableMfaDialogProps {
  open: boolean;
  onDisabled: () => void;
  onOpenChange: (open: boolean) => void;
}

export function DisableMfaDialog({
  open,
  onDisabled,
  onOpenChange,
}: DisableMfaDialogProps) {
  const t = useTranslations("security.mfa.disableDialog");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const disableMutation = useMfaDisableMutation();

  function resetForm() {
    setPassword("");
    setTotpCode("");
    setErrorMessage(null);
    disableMutation.reset();
  }

  async function submit() {
    setErrorMessage(null);
    try {
      await disableMutation.mutateAsync({
        password,
        totp_code: totpCode,
      });
      toast({ title: t("successTitle"), variant: "success" });
      resetForm();
      onDisabled();
      onOpenChange(false);
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : t("error"));
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          resetForm();
        }
        onOpenChange(nextOpen);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>{t("description")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="disable-mfa-password">{t("password")}</Label>
            <Input
              id="disable-mfa-password"
              autoComplete="current-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="disable-mfa-code">{t("code")}</Label>
            <InputOTP
              id="disable-mfa-code"
              aria-label={t("codeAria")}
              inputMode="numeric"
              maxLength={6}
              onChange={setTotpCode}
              placeholder="000000"
              value={totpCode}
            />
          </div>
          {errorMessage ? (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {errorMessage}
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            {t("cancel")}
          </Button>
          <Button
            type="button"
            variant="destructive"
            disabled={!password || totpCode.length < 6 || disableMutation.isPending}
            onClick={() => void submit()}
          >
            {disableMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ShieldOff className="h-4 w-4" />
            )}
            {disableMutation.isPending ? t("submitting") : t("submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
