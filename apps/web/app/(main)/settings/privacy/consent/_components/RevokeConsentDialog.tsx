"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { useRevokeConsent } from "@/lib/hooks/use-me-consent";

interface RevokeConsentDialogProps {
  consentType: string;
  disabled?: boolean;
}

export function RevokeConsentDialog({ consentType, disabled }: RevokeConsentDialogProps) {
  const t = useTranslations("privacy.consent.revoke");
  const [open, setOpen] = useState(false);
  const revoke = useRevokeConsent();

  function confirm() {
    revoke.mutate(
      { consent_type: consentType },
      {
        onSuccess: () => setOpen(false),
      },
    );
  }

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger asChild>
        <Button disabled={disabled} size="sm" variant="outline">
          {t("trigger")}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("title")}</AlertDialogTitle>
          <AlertDialogDescription>
            {t("description", { consentType })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            {t("cancel")}
          </Button>
          <Button disabled={revoke.isPending} variant="destructive" onClick={confirm}>
            {t("confirm")}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
