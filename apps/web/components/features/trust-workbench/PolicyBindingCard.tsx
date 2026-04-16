"use client";

import { useState } from "react";
import { ExternalLink, ShieldMinus } from "lucide-react";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { PolicyBinding } from "@/lib/types/trust-workbench";

export interface PolicyBindingCardProps {
  binding: PolicyBinding;
  onRemove?: ((attachmentId: string) => void) | undefined;
}

export function PolicyBindingCard({
  binding,
  onRemove,
}: PolicyBindingCardProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);

  return (
    <>
      <Card className="rounded-[1.5rem] border-border/60 bg-card/80">
        <CardContent className="flex flex-col gap-4 p-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-medium">{binding.policyName}</p>
              <Badge variant="outline">{binding.scopeType}</Badge>
              <Badge
                className={
                  binding.isActive
                    ? "border-emerald-500/30 bg-emerald-500/12 text-emerald-700 dark:text-emerald-300"
                    : "border-border/80 bg-muted/70 text-muted-foreground"
                }
                variant="outline"
              >
                {binding.isActive ? "active" : "suspended"}
              </Badge>
            </div>
            {binding.policyDescription ? (
              <p className="text-sm text-muted-foreground">
                {binding.policyDescription}
              </p>
            ) : null}
            <Badge className="w-fit" variant="outline">
              {binding.sourceLabel ?? binding.source}
            </Badge>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {binding.canRemove && onRemove ? (
              <Button
                size="sm"
                variant="destructive"
                onClick={() => setConfirmOpen(true)}
              >
                <ShieldMinus className="h-4 w-4" />
                Remove
              </Button>
            ) : binding.sourceEntityUrl ? (
              <Button asChild size="sm" variant="outline">
                <a href={binding.sourceEntityUrl}>
                  Manage -&gt;
                  <ExternalLink className="h-4 w-4" />
                </a>
              </Button>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <ConfirmDialog
        confirmLabel="Remove policy"
        description="Removing this policy will affect enforcement immediately."
        onConfirm={() => {
          onRemove?.(binding.attachmentId);
          setConfirmOpen(false);
        }}
        onOpenChange={setConfirmOpen}
        open={confirmOpen}
        title="Remove direct policy binding?"
        variant="destructive"
      />
    </>
  );
}
