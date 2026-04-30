"use client";

import { useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const SOURCES = ["memory", "knowledgeGraph", "executionHistory", "toolOutputs", "externalApis"] as const;

export function SourcePicker() {
  const t = useTranslations("creator.contextProfile");

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("sources")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        {SOURCES.map((source) => (
          <Badge key={source} variant="secondary">
            {t(source)}
          </Badge>
        ))}
      </CardContent>
    </Card>
  );
}
