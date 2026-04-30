"use client";

import { useTranslations } from "next-intl";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function WebhookWizardSteps() {
  const t = useTranslations("workspaces.connectors.wizard.webhook");

  return (
    <div className="space-y-3">
      <Alert>
        <AlertTitle>{t("title")}</AlertTitle>
        <AlertDescription>{t("description")}</AlertDescription>
      </Alert>
      <div className="space-y-2">
        <Label>{t("destinationUrl")}</Label>
        <Input placeholder="https://hooks.example.com/workspace" />
      </div>
    </div>
  );
}
