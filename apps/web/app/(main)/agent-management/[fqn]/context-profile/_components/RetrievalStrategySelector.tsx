"use client";

import { useTranslations } from "next-intl";
import { Toggle } from "@/components/ui/toggle";

const STRATEGIES = ["semantic", "graph", "fts", "hybrid"] as const;

export function RetrievalStrategySelector() {
  const t = useTranslations("creator.contextProfile");

  return (
    <div className="rounded-lg border p-4">
      <p className="text-sm font-medium">{t("retrievalStrategy")}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {STRATEGIES.map((strategy) => (
          <Toggle key={strategy} aria-label={t(strategy)} pressed={strategy === "hybrid"}>
            {t(strategy)}
          </Toggle>
        ))}
      </div>
    </div>
  );
}
