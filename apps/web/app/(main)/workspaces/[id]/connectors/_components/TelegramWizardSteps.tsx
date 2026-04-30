"use client";

import { useTranslations } from "next-intl";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function TelegramWizardSteps() {
  const t = useTranslations("workspaces.connectors.wizard.telegram");

  return (
    <div className="space-y-3">
      <Alert>
        <AlertTitle>{t("title")}</AlertTitle>
        <AlertDescription>{t("description")}</AlertDescription>
      </Alert>
      <div className="space-y-2">
        <Label>{t("botTokenRef")}</Label>
        <Input placeholder="bot_token" />
      </div>
    </div>
  );
}
