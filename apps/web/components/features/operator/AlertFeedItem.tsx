"use client";

import { useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { ChevronDown, ChevronUp } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Badge } from "@/components/ui/badge";
import {
  ALERT_SEVERITY_LABELS,
  type AlertSeverity,
  type OperatorAlert,
} from "@/lib/types/operator-dashboard";

export interface AlertFeedItemProps {
  alert: OperatorAlert;
}

const severityTone: Record<AlertSeverity, string> = {
  info: "border-blue-500/30 bg-blue-500/12 text-blue-700 dark:text-blue-300",
  warning:
    "border-amber-500/30 bg-amber-500/12 text-amber-700 dark:text-amber-300",
  error:
    "border-orange-500/30 bg-orange-500/12 text-orange-700 dark:text-orange-300",
  critical: "border-destructive/30 bg-destructive/10 text-foreground",
};

export function AlertFeedItem({ alert }: AlertFeedItemProps) {
  const [open, setOpen] = useState(false);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className="rounded-xl border border-border/60 bg-background/70">
        <CollapsibleTrigger
          aria-expanded={open}
          className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left"
        >
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge className={severityTone[alert.severity]} variant="outline">
                {ALERT_SEVERITY_LABELS[alert.severity]}
              </Badge>
              <span className="text-sm font-medium">{alert.sourceService}</span>
              <span className="text-xs text-muted-foreground">
                {formatDistanceToNow(new Date(alert.timestamp), { addSuffix: true })}
              </span>
            </div>
            <p className="text-sm text-foreground">{alert.message}</p>
          </div>
          {open ? (
            <ChevronUp className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronDown className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" />
          )}
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="space-y-3 border-t border-border/60 px-4 py-3 text-sm">
            {alert.description ? (
              <div>
                <p className="font-medium">Description</p>
                <p className="text-muted-foreground">{alert.description}</p>
              </div>
            ) : null}
            {alert.suggestedAction ? (
              <div>
                <p className="font-medium">Suggested action</p>
                <p className="text-muted-foreground">{alert.suggestedAction}</p>
              </div>
            ) : null}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}
