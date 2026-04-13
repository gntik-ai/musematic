"use client";

import { useState } from "react";
import { SlidersHorizontal, X } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  CERTIFICATION_STATUSES,
  COST_TIERS,
  MATURITY_LEVELS,
  TRUST_TIERS,
  humanizeMarketplaceValue,
  type CertificationStatus,
  type CostTier,
  type FilterMetadata,
  type MarketplaceSearchParams,
  type MaturityLevel,
  type TrustTier,
} from "@/lib/types/marketplace";

export interface FilterSidebarProps {
  filters: Partial<MarketplaceSearchParams>;
  filterMetadata: FilterMetadata;
  onChange: (updated: Partial<MarketplaceSearchParams>) => void;
  activeFilterCount: number;
  isMobile: boolean;
}

function toggleValue<T extends string>(values: T[], target: T): T[] {
  return values.includes(target)
    ? values.filter((value) => value !== target)
    : [...values, target];
}

function FilterGroup({
  title,
  options,
  selected,
  onToggle,
}: {
  title: string;
  options: string[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  return (
    <section className="space-y-3">
      <h3 className="text-sm font-semibold">{title}</h3>
      <div className="space-y-2">
        {options.map((option) => {
          const checked = selected.includes(option);

          return (
            <label
              key={option}
              className="flex cursor-pointer items-center justify-between gap-3 rounded-xl border border-border/60 bg-background/70 px-3 py-2 text-sm transition hover:bg-accent/50"
            >
              <span>{humanizeMarketplaceValue(option)}</span>
              <Checkbox
                checked={checked}
                onChange={() => onToggle(option)}
              />
            </label>
          );
        })}
      </div>
    </section>
  );
}

function SidebarContent({
  activeFilterCount,
  filterMetadata,
  filters,
  onChange,
}: Omit<FilterSidebarProps, "isMobile">) {
  const clearAll = () => {
    onChange({
      capabilities: [],
      maturityLevels: [],
      trustTiers: [],
      certificationStatuses: [],
      costTiers: [],
      tags: [],
    });
  };

  return (
    <nav aria-label="Agent filters" className="space-y-6" role="navigation">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.16em] text-brand-accent">
            Filters
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Narrow results by trust, maturity, cost, and capabilities.
          </p>
        </div>
        {activeFilterCount > 0 ? (
          <Button size="sm" variant="ghost" onClick={clearAll}>
            <X className="h-4 w-4" />
            Clear all
          </Button>
        ) : null}
      </div>

      <FilterGroup
        title="Maturity level"
        options={[...MATURITY_LEVELS]}
        selected={filters.maturityLevels ?? []}
        onToggle={(value) =>
          onChange({
            maturityLevels: toggleValue(
              filters.maturityLevels ?? [],
              value as MaturityLevel,
            ),
          })
        }
      />
      <FilterGroup
        title="Trust tier"
        options={[...TRUST_TIERS]}
        selected={filters.trustTiers ?? []}
        onToggle={(value) =>
          onChange({
            trustTiers: toggleValue(filters.trustTiers ?? [], value as TrustTier),
          })
        }
      />
      <FilterGroup
        title="Certification status"
        options={[...CERTIFICATION_STATUSES]}
        selected={filters.certificationStatuses ?? []}
        onToggle={(value) =>
          onChange({
            certificationStatuses: toggleValue(
              filters.certificationStatuses ?? [],
              value as CertificationStatus,
            ),
          })
        }
      />
      <FilterGroup
        title="Cost tier"
        options={[...COST_TIERS]}
        selected={filters.costTiers ?? []}
        onToggle={(value) =>
          onChange({
            costTiers: toggleValue(filters.costTiers ?? [], value as CostTier),
          })
        }
      />
      <FilterGroup
        title="Capabilities"
        options={filterMetadata.capabilities}
        selected={filters.capabilities ?? []}
        onToggle={(value) =>
          onChange({
            capabilities: toggleValue(filters.capabilities ?? [], value),
          })
        }
      />
      <FilterGroup
        title="Tags"
        options={filterMetadata.tags}
        selected={filters.tags ?? []}
        onToggle={(value) =>
          onChange({
            tags: toggleValue(filters.tags ?? [], value),
          })
        }
      />
    </nav>
  );
}

export function FilterSidebar({
  activeFilterCount,
  filterMetadata,
  filters,
  onChange,
  isMobile,
}: FilterSidebarProps) {
  const [open, setOpen] = useState(false);

  if (isMobile) {
    return (
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger asChild>
          <Button className="w-full justify-between rounded-2xl" variant="outline">
            <span className="flex items-center gap-2">
              <SlidersHorizontal className="h-4 w-4" />
              Filters ({activeFilterCount})
            </span>
            <span className="text-xs text-muted-foreground">Refine results</span>
          </Button>
        </SheetTrigger>
        <SheetContent className="max-h-[90vh] overflow-auto">
          <SheetTitle>Agent filters</SheetTitle>
          <SheetDescription>
            Refine marketplace results by trust, maturity, cost, and capability.
          </SheetDescription>
          <div className="mt-6">
            <SidebarContent
              activeFilterCount={activeFilterCount}
              filterMetadata={filterMetadata}
              filters={filters}
              onChange={onChange}
            />
          </div>
        </SheetContent>
      </Sheet>
    );
  }

  return (
    <aside className="rounded-3xl border border-border/60 bg-card/70 p-5 shadow-sm">
      <SidebarContent
        activeFilterCount={activeFilterCount}
        filterMetadata={filterMetadata}
        filters={filters}
        onChange={onChange}
      />
    </aside>
  );
}
