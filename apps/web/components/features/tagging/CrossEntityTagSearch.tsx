"use client";

import { Input } from "@/components/ui/input";
import type { TaggableEntityType } from "@/lib/api/tagging";
import { useCrossEntityTagSearch } from "@/lib/api/tagging";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";

const detailRoutes: Record<TaggableEntityType, (id: string) => string> = {
  agent: (id) => `/agent-management/${encodeURIComponent(id)}`,
  certification: (id) => `/trust-workbench/${encodeURIComponent(id)}`,
  evaluation_run: (id) => `/evaluation-testing?run_id=${encodeURIComponent(id)}`,
  fleet: (id) => `/fleet/${encodeURIComponent(id)}`,
  policy: (id) => `/policies?policy_id=${encodeURIComponent(id)}`,
  workflow: (id) => `/workflow-editor-monitor/${encodeURIComponent(id)}`,
  workspace: (id) => `/settings?workspace_id=${encodeURIComponent(id)}`,
};

export function CrossEntityTagSearch() {
  const [query, setQuery] = useState("");
  const tag = useMemo(() => query.trim().replace(/^tag:/, ""), [query]);
  const { data } = useCrossEntityTagSearch(tag);
  const grouped = Object.entries(data?.entities ?? {});

  return (
    <div className="space-y-2">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden="true" />
        <Input
          aria-label="Cross-entity tag search"
          className="pl-9"
          onChange={(event) => setQuery(event.target.value)}
          value={query}
        />
      </div>
      <div className="grid gap-1">
        {grouped.map(([entityType, ids]) => {
          const routeFor = detailRoutes[entityType as TaggableEntityType];
          return (
            <div className="rounded-md border border-border px-2 py-1 text-sm" key={entityType}>
              <div>
                <span className="font-medium">{entityType}</span>
                <span className="ml-2 text-muted-foreground">{ids.length}</span>
              </div>
              <div className="mt-1 flex flex-wrap gap-1">
                {ids.map((id) => (
                  <a
                    className="rounded-sm px-1.5 py-0.5 text-xs text-primary hover:bg-accent"
                    href={routeFor(id)}
                    key={id}
                  >
                    {id}
                  </a>
                ))}
              </div>
          </div>
          );
        })}
      </div>
    </div>
  );
}
