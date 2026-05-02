"use client";

import { ExternalLink, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useMemberships } from "@/lib/hooks/use-memberships";

export default function MembershipsPage() {
  const { isLoading, memberships } = useMemberships();

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Tenant memberships</h1>
        <p className="text-sm text-muted-foreground">
          Review every tenant identity associated with your email.
        </p>
      </div>

      {isLoading ? (
        <div className="flex min-h-48 items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-brand-accent" />
        </div>
      ) : null}

      <div className="grid gap-3">
        {memberships.map((membership) => (
          <div
            key={membership.tenant_id}
            className="flex flex-col gap-3 rounded-md border border-border/70 bg-card p-4 sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="truncate text-base font-semibold">
                  {membership.tenant_display_name}
                </h2>
                {membership.is_current ? <Badge variant="secondary">Current</Badge> : null}
                <Badge variant="outline">{membership.tenant_kind}</Badge>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {membership.role.replaceAll("_", " ")} · {membership.tenant_slug}
              </p>
            </div>
            <Button
              className="shrink-0"
              type="button"
              variant={membership.is_current ? "outline" : "default"}
              onClick={() => window.location.assign(membership.login_url)}
            >
              <ExternalLink className="h-4 w-4" />
              {membership.is_current ? "Open login" : "Switch"}
            </Button>
          </div>
        ))}
      </div>

      {!isLoading && memberships.length === 0 ? (
        <div className="rounded-md border border-border/70 p-6 text-sm text-muted-foreground">
          No memberships found.
        </div>
      ) : null}
    </div>
  );
}
