"use client";

import { GripVertical } from "lucide-react";
import { useTranslations } from "next-intl";

const RULES = ["score", "recency", "authority", "customExpression"] as const;

export function RerankingRulesEditor() {
  const t = useTranslations("creator.contextProfile");

  return (
    <div className="space-y-2 rounded-lg border p-4">
      <p className="text-sm font-medium">{t("rerankingRules")}</p>
      {RULES.map((rule) => (
        <div key={rule} className="flex items-center gap-2 rounded-md border bg-card p-2 text-sm">
          <GripVertical className="h-4 w-4 text-muted-foreground" />
          {t(rule)}
        </div>
      ))}
    </div>
  );
}
