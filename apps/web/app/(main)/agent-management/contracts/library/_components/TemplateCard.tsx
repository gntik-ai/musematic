"use client";

import type { ReactNode } from "react";
import { useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import type { ContractTemplate } from "@/lib/api/creator-uis";

export function TemplateCard({
  template,
  action,
}: {
  template: ContractTemplate;
  action?: ReactNode;
}) {
  const t = useTranslations("creator.template");

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">{template.name}</CardTitle>
          <Badge variant={template.is_platform_authored ? "secondary" : "outline"}>
            {template.category}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">{template.description}</p>
        <p className="mt-3 text-xs text-muted-foreground">
          {t("version")} {template.version_number}
        </p>
      </CardContent>
      {action ? <CardFooter>{action}</CardFooter> : null}
    </Card>
  );
}
