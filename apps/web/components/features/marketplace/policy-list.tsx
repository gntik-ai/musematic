"use client";

import { Badge } from "@/components/ui/badge";
import { type PolicyEnforcement, type PolicySummary } from "@/lib/types/marketplace";

export interface PolicyListProps {
  policies: PolicySummary[];
}

const enforcementVariant: Record<
  PolicyEnforcement,
  "destructive" | "secondary" | "outline"
> = {
  block: "destructive",
  warn: "secondary",
  log: "outline",
};

export function PolicyList({ policies }: PolicyListProps) {
  if (policies.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-border px-4 py-6 text-sm text-muted-foreground">
        No policies are attached to this agent yet.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {policies.map((policy) => (
        <div
          key={policy.id}
          className="rounded-2xl border border-border/60 bg-card/70 p-4"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="font-medium">{policy.name}</p>
              <p className="text-sm text-muted-foreground">{policy.type}</p>
            </div>
            <Badge variant={enforcementVariant[policy.enforcement]}>
              {policy.enforcement.toUpperCase()}
            </Badge>
          </div>
          <p className="mt-3 text-sm text-muted-foreground">
            {policy.description}
          </p>
        </div>
      ))}
    </div>
  );
}
