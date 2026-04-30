"use client";

import { useTranslations } from "next-intl";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function EmailWizardSteps() {
  const t = useTranslations("workspaces.connectors.wizard.email");

  return (
    <div className="space-y-3">
      <Alert>
        <AlertTitle>{t("title")}</AlertTitle>
        <AlertDescription>{t("description")}</AlertDescription>
      </Alert>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-2"><Label>{t("imapHost")}</Label><Input placeholder="imap.example.com" /></div>
        <div className="space-y-2"><Label>{t("smtpHost")}</Label><Input placeholder="smtp.example.com" /></div>
      </div>
    </div>
  );
}
