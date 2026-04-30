"use client";

import { Tags } from "lucide-react";
import { useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function TagSummaryCard({ tags }: { tags: Record<string, unknown> }) {
  const t = useTranslations("workspaces.dashboard");
  const items = Array.isArray(tags.items) ? tags.items.slice(0, 4) : [];
  const count = typeof tags.count === "number" ? tags.count : items.length;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Tags className="h-4 w-4" />
          {t("cards.tagSummary")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-3xl font-semibold">{count}</p>
        <div className="flex flex-wrap gap-2">
          {items.length ? (
            items.map((item) => (
              <Badge key={String(item)} variant="secondary">
                {String(item)}
              </Badge>
            ))
          ) : (
            <span className="text-xs text-muted-foreground">{t("noTags")}</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
