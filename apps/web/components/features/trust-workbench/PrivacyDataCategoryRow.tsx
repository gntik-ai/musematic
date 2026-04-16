"use client";

import { AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { PrivacyDataCategory } from "@/lib/types/trust-workbench";

export interface PrivacyDataCategoryRowProps {
  category: PrivacyDataCategory;
}

const statusClasses = {
  compliant: "border-emerald-500/30 bg-emerald-500/12 text-emerald-700 dark:text-emerald-300",
  warning: "border-amber-500/30 bg-amber-500/12 text-amber-700 dark:text-amber-300",
  violation: "border-destructive/30 bg-destructive/10 text-foreground",
} as const;

export function PrivacyDataCategoryRow({
  category,
}: PrivacyDataCategoryRowProps) {
  return (
    <Card className="rounded-[1.5rem] border-border/60 bg-card/80">
      <CardContent className="space-y-4 p-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="space-y-1">
            <p className="font-medium">{category.name}</p>
            <p className="text-sm text-muted-foreground">
              Retention: {category.retentionDuration ?? "Not specified"}
            </p>
          </div>
          <Badge className={statusClasses[category.complianceStatus]} variant={category.complianceStatus === "violation" ? "destructive" : "outline"}>
            {category.complianceStatus}
          </Badge>
        </div>

        {category.complianceStatus !== "compliant" ? (
          <div className="space-y-3">
            {category.concerns.map((concern, index) => (
              <div
                key={`${category.name}-${concern.description}`}
                className="rounded-2xl border border-destructive/20 bg-destructive/5 p-4"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-destructive" />
                  <p className="font-medium">{concern.description}</p>
                  <Badge variant="outline">{concern.severity}</Badge>
                </div>
                {category.recommendations[index] ? (
                  <p className="mt-2 text-sm text-muted-foreground">
                    Recommendation: {category.recommendations[index]}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
