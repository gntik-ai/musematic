"use client";

import { FilterX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";

export interface FilterOption {
  label: string;
  value: string;
}

export interface FilterDefinition {
  id: string;
  label: string;
  value: string | string[];
  options: FilterOption[];
  multiple?: boolean;
}

export function FilterBar({
  filters,
  onChange,
  onClear,
}: {
  filters: FilterDefinition[];
  onChange: (id: string, value: string | string[]) => void;
  onClear: () => void;
}) {
  const activeCount = filters.filter((filter) =>
    Array.isArray(filter.value) ? filter.value.length > 0 : filter.value.length > 0,
  ).length;

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-border bg-card/80 p-4">
      {filters.map((filter) => (
        <label key={filter.id} className="min-w-40 space-y-2 text-sm">
          <span className="font-medium">{filter.label}</span>
          <Select
            className={filter.multiple ? "min-h-24" : undefined}
            multiple={filter.multiple}
            value={filter.value}
            onChange={(event) => {
              if (filter.multiple) {
                onChange(
                  filter.id,
                  Array.from(event.currentTarget.selectedOptions, (option) => option.value),
                );
                return;
              }

              onChange(filter.id, event.target.value);
            }}
          >
            {!filter.multiple ? <option value="">All</option> : null}
            {filter.options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </label>
      ))}
      {activeCount > 0 ? (
        <Button className="ml-auto gap-2" variant="ghost" onClick={onClear}>
          <FilterX className="h-4 w-4" />
          Clear all
        </Button>
      ) : null}
    </div>
  );
}
