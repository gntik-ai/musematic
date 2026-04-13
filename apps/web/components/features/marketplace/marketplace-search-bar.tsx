"use client";

import { useEffect, useState } from "react";
import { Loader2, Search, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Input } from "@/components/ui/input";
import { useDebouncedValue } from "@/lib/hooks/use-debounced-value";

export interface MarketplaceSearchBarProps {
  initialValue: string;
  onSearch: (query: string) => void;
  isLoading: boolean;
}

export function MarketplaceSearchBar({
  initialValue,
  onSearch,
  isLoading,
}: MarketplaceSearchBarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [value, setValue] = useState(initialValue);
  const debouncedValue = useDebouncedValue(value, 300);

  useEffect(() => {
    setValue(initialValue);
  }, [initialValue]);

  useEffect(() => {
    onSearch(debouncedValue);

    const nextParams = new URLSearchParams(searchParams.toString());
    if (debouncedValue) {
      nextParams.set("q", debouncedValue);
    } else {
      nextParams.delete("q");
    }

    const nextQuery = nextParams.toString();
    const currentQuery = searchParams.toString();

    if (nextQuery !== currentQuery) {
      router.push(nextQuery ? `${pathname}?${nextQuery}` : pathname);
    }
  }, [debouncedValue, onSearch, pathname, router, searchParams]);

  return (
    <form className="relative" role="search" onSubmit={(event) => event.preventDefault()}>
      <span className="pointer-events-none absolute inset-y-0 left-4 flex items-center text-muted-foreground">
        {isLoading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Search className="h-4 w-4" />
        )}
      </span>
      <Input
        aria-label="Search agents"
        className="h-12 rounded-2xl border-border/70 bg-card/80 pl-11 pr-12 shadow-sm"
        placeholder="Search by task, capability, or agent name"
        value={value}
        onChange={(event) => setValue(event.target.value)}
      />
      {value ? (
        <button
          aria-label="Clear search"
          className="absolute inset-y-0 right-4 flex items-center text-muted-foreground transition hover:text-foreground"
          type="button"
          onClick={() => setValue("")}
        >
          <X className="h-4 w-4" />
        </button>
      ) : null}
    </form>
  );
}
