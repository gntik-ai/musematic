"use client";

import { Gauge } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

const quotaKeys = ["agents", "fleets", "executions", "storage_gb"] as const;

export function QuotaUsageBarsCard({ quotas }: { quotas: Record<string, unknown> }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Gauge className="h-4 w-4" />
          Quotas
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {quotaKeys.map((key) => {
          const raw = quotas[key];
          const limit = typeof raw === "number" ? raw : Number(raw ?? 0);
          const value = limit > 0 ? Math.min(100, Math.round((limit / Math.max(limit, 1)) * 100)) : 0;
          return (
            <div key={key} className="space-y-1">
              <div className="flex justify-between text-xs">
                <span className="capitalize text-muted-foreground">{key.replace("_", " ")}</span>
                <span>{limit || "unset"}</span>
              </div>
              <Progress value={value} />
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
