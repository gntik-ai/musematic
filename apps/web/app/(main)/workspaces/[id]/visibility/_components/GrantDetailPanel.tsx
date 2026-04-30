"use client";

import { useTranslations } from "next-intl";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export interface GrantDetail {
  direction: "given" | "received";
  label: string;
  pattern: string;
}

export function GrantDetailPanel({ grant }: { grant: GrantDetail | null }) {
  const t = useTranslations("workspaces.visibility.detail");

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">{t("title")}</CardTitle></CardHeader>
      <CardContent>
        {grant ? (
          <dl className="space-y-3 text-sm">
            <div><dt className="text-muted-foreground">{t("direction")}</dt><dd>{grant.direction}</dd></div>
            <div><dt className="text-muted-foreground">{t("label")}</dt><dd>{grant.label}</dd></div>
            <div><dt className="text-muted-foreground">{t("pattern")}</dt><dd className="font-mono text-xs">{grant.pattern}</dd></div>
          </dl>
        ) : (
          <p className="text-sm text-muted-foreground">{t("empty")}</p>
        )}
      </CardContent>
    </Card>
  );
}
