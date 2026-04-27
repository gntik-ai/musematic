"use client";

import { GripVertical } from "lucide-react";

const RULES = ["Score", "Recency", "Authority", "Custom expression"];

export function RerankingRulesEditor() {
  return (
    <div className="space-y-2 rounded-lg border p-4">
      <p className="text-sm font-medium">Reranking Rules</p>
      {RULES.map((rule) => (
        <div key={rule} className="flex items-center gap-2 rounded-md border bg-card p-2 text-sm">
          <GripVertical className="h-4 w-4 text-muted-foreground" />
          {rule}
        </div>
      ))}
    </div>
  );
}

