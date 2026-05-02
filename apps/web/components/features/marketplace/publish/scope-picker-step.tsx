"use client";

/**
 * UPD-049 — Scope picker step for the agent publish flow.
 *
 * Renders three clickable Card options (workspace / tenant / public). The
 * `public_default_tenant` option is disabled with a tooltip when the
 * caller's tenant is not the default tenant — the UI leg of the
 * three-layer Enterprise refusal (FR-010). The other two layers (service
 * guard + DB CHECK) live on the backend.
 */

import { Building2, Globe2, Lock } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { MarketplaceScope } from "@/lib/marketplace/types";

const PUBLIC_DISABLED_TOOLTIP =
  "Public publishing is only available in the SaaS public tenant.";

export interface ScopePickerStepProps {
  /** The scope currently selected by the user. */
  value: MarketplaceScope;
  onChange: (next: MarketplaceScope) => void;
  /**
   * Tenant kind from the resolved tenant context. The publish flow gets
   * this from the auth/store; we accept it as a prop so the picker is
   * test-friendly and rendering-pure.
   */
  tenantKind: "default" | "enterprise";
  className?: string;
}

interface ScopeOption {
  scope: MarketplaceScope;
  title: string;
  description: string;
  icon: typeof Lock;
}

const SCOPE_OPTIONS: ScopeOption[] = [
  {
    scope: "workspace",
    title: "Workspace",
    description: "Visible only inside the workspace where you publish.",
    icon: Lock,
  },
  {
    scope: "tenant",
    title: "Tenant",
    description: "Visible to every workspace inside this tenant.",
    icon: Building2,
  },
  {
    scope: "public_default_tenant",
    title: "Public marketplace",
    description: "Visible to all default-tenant users plus opted-in Enterprise tenants.",
    icon: Globe2,
  },
];

export function ScopePickerStep({
  value,
  onChange,
  tenantKind,
  className,
}: ScopePickerStepProps) {
  return (
    <TooltipProvider>
      <div
        className={cn("grid gap-3 sm:grid-cols-3", className)}
        role="radiogroup"
        aria-label="Marketplace scope"
      >
        {SCOPE_OPTIONS.map((option) => {
          const isPublic = option.scope === "public_default_tenant";
          const isDisabled = isPublic && tenantKind !== "default";
          const isSelected = value === option.scope;

          const card = (
            <Card
              role="radio"
              aria-checked={isSelected}
              aria-disabled={isDisabled}
              tabIndex={isDisabled ? -1 : 0}
              data-testid={`scope-picker-${option.scope}`}
              onClick={() => {
                if (!isDisabled) onChange(option.scope);
              }}
              onKeyDown={(event) => {
                if (isDisabled) return;
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onChange(option.scope);
                }
              }}
              className={cn(
                "cursor-pointer transition focus:outline-none focus:ring-2 focus:ring-primary",
                isSelected && "border-primary ring-1 ring-primary",
                isDisabled && "cursor-not-allowed opacity-60",
              )}
            >
              <CardHeader className="flex flex-row items-center gap-3 space-y-0 pb-2">
                <option.icon className="h-5 w-5 text-muted-foreground" aria-hidden />
                <CardTitle className="text-base">{option.title}</CardTitle>
              </CardHeader>
              <CardContent>
                <CardDescription>{option.description}</CardDescription>
              </CardContent>
            </Card>
          );

          if (!isDisabled) {
            return <div key={option.scope}>{card}</div>;
          }
          // Disabled public option — wrap with a tooltip explaining why.
          return (
            <Tooltip key={option.scope}>
              <TooltipTrigger>{card}</TooltipTrigger>
              <TooltipContent>{PUBLIC_DISABLED_TOOLTIP}</TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    </TooltipProvider>
  );
}
