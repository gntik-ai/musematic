"use client";

import { useEffect, useState } from "react";
import { Loader2, Search, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Input } from "@/components/ui/input";
import { useDebouncedValue } from "@/lib/hooks/use-debounced-value";

export interface MarketplaceSearchFqnProps {
  initialQuery?: string;
  isLoading?: boolean;
  onQueryChange: (query: string) => void;
}

export function MarketplaceSearchFqn({
  initialQuery = "",
  isLoading = false,
  onQueryChange,
}: MarketplaceSearchFqnProps) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [query, setQuery] = useState(initialQuery);
  const debouncedQuery = useDebouncedValue(query, 300);

  useEffect(() => {
    setQuery(initialQuery);
  }, [initialQuery]);

  useEffect(() => {
    onQueryChange(debouncedQuery);

    const nextParams = new URLSearchParams(searchParams.toString());
    if (debouncedQuery.trim()) {
      nextParams.set("q", debouncedQuery.trim());
    } else {
      nextParams.delete("q");
    }

    const nextQuery = nextParams.toString();
    if (nextQuery !== searchParams.toString()) {
      router.push(nextQuery ? `${pathname}?${nextQuery}` : pathname);
    }
  }, [debouncedQuery, onQueryChange, pathname, router, searchParams]);

  return (
    <form className="relative" role="search" onSubmit={(event) => event.preventDefault()}>
      <span className="pointer-events-none absolute inset-y-0 left-4 flex items-center text-muted-foreground">
        {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
      </span>
      <Input
        aria-label="Search agents by FQN"
        className="h-12 rounded-2xl border-border/70 bg-card/80 pl-11 pr-12 shadow-sm"
        placeholder="Search by FQN prefix, for example ops: or research:"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      {query ? (
        <button
          aria-label="Clear search"
          className="absolute inset-y-0 right-4 flex items-center text-muted-foreground transition hover:text-foreground"
          type="button"
          onClick={() => setQuery("")}
        >
          <X className="h-4 w-4" />
        </button>
      ) : null}
    </form>
  );
}
