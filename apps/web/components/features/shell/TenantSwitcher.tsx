"use client";

import { Check, ChevronsUpDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useMemberships } from "@/lib/hooks/use-memberships";

export function TenantSwitcher() {
  const { currentMembership, isLoading, memberships } = useMemberships();

  if (isLoading || memberships.length < 2) {
    return null;
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button className="max-w-64 gap-2" variant="outline">
          <span className="min-w-0 truncate">
            {currentMembership?.tenant_display_name ?? "Tenants"}
          </span>
          <ChevronsUpDown className="h-4 w-4 shrink-0 text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-80">
        <DropdownMenuLabel>Switch tenant</DropdownMenuLabel>
        {memberships.map((membership) => (
          <DropdownMenuItem
            key={membership.tenant_id}
            className="items-start gap-3"
            onClick={() => {
              if (!membership.is_current) {
                window.location.assign(membership.login_url);
              }
            }}
          >
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="truncate font-medium">{membership.tenant_display_name}</span>
              <span className="text-xs text-muted-foreground">
                {membership.role.replaceAll("_", " ")} · {membership.tenant_kind}
              </span>
            </span>
            {membership.is_current ? <Check className="h-4 w-4 text-brand-primary" /> : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
