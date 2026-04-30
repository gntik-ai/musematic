"use client";

import { useTranslations } from "next-intl";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function ContextBudgetControls() {
  const t = useTranslations("creator.contextProfile");

  return (
    <div className="grid gap-4 rounded-lg border p-4 sm:grid-cols-2">
      <div className="space-y-2">
        <Label htmlFor="max-tokens">{t("maxTokens")}</Label>
        <Input id="max-tokens" min={1} type="number" value={8192} readOnly />
      </div>
      <div className="space-y-2">
        <Label htmlFor="max-documents">{t("maxDocuments")}</Label>
        <Input id="max-documents" min={1} type="number" value={50} readOnly />
      </div>
    </div>
  );
}
