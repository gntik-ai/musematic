"use client";

import { Toggle } from "@/components/ui/toggle";

const STRATEGIES = ["semantic", "graph", "fts", "hybrid"];

export function RetrievalStrategySelector() {
  return (
    <div className="rounded-lg border p-4">
      <p className="text-sm font-medium">Retrieval Strategy</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {STRATEGIES.map((strategy) => (
          <Toggle key={strategy} aria-label={strategy} pressed={strategy === "hybrid"}>
            {strategy}
          </Toggle>
        ))}
      </div>
    </div>
  );
}

