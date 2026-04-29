"use client";

import { Input } from "@/components/ui/input";
import { useCrossEntityTagSearch } from "@/lib/api/tagging";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";

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
        {grouped.map(([entityType, ids]) => (
          <div className="rounded-md border border-border px-2 py-1 text-sm" key={entityType}>
            <span className="font-medium">{entityType}</span>
            <span className="ml-2 text-muted-foreground">{ids.length}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
