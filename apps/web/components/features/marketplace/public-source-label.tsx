"use client";

/**
 * UPD-049 — Tag rendered on marketplace listing rows whose
 * `marketplace_scope='public_default_tenant'` and whose tenant context
 * is NOT the default tenant. Tells the consumer "this came from the
 * public hub" so they understand why a non-tenant agent is in their
 * search results.
 */

import { Globe2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface PublicSourceLabelProps {
  className?: string;
}

export function PublicSourceLabel({ className }: PublicSourceLabelProps) {
  return (
    <Badge variant="secondary" className={cn("gap-1", className)}>
      <Globe2 className="h-3 w-3" aria-hidden />
      From public marketplace
    </Badge>
  );
}
