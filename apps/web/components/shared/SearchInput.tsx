"use client";

import { useEffect, useState } from "react";
import { Loader2, Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";

export function SearchInput({
  defaultValue = "",
  isLoading = false,
  onChange,
  placeholder = "Search",
}: {
  defaultValue?: string;
  isLoading?: boolean;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  const [value, setValue] = useState(defaultValue);

  useEffect(() => {
    const timer = window.setTimeout(() => onChange(value), 300);
    return () => window.clearTimeout(timer);
  }, [onChange, value]);

  return (
    <div className="relative">
      <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-muted-foreground">
        {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
      </span>
      <Input
        aria-label={placeholder}
        className="pl-10 pr-10"
        placeholder={placeholder}
        value={value}
        onChange={(event) => setValue(event.target.value)}
      />
      {value ? (
        <button
          aria-label="Clear search"
          className="absolute inset-y-0 right-3 flex items-center text-muted-foreground"
          type="button"
          onClick={() => setValue("")}
        >
          <X className="h-4 w-4" />
        </button>
      ) : null}
    </div>
  );
}
