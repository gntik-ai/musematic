"use client";

import { useMemo, useState } from "react";
import { format } from "date-fns";
import { ChevronDown, ChevronUp } from "lucide-react";
import { JsonViewer } from "@/components/shared/JsonViewer";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { EVIDENCE_TYPE_LABELS, type EvidenceItem, type EvidenceResult } from "@/lib/types/trust-workbench";
import { cn } from "@/lib/utils";

export interface EvidenceItemCardProps {
  item: EvidenceItem;
}

const resultClasses: Record<EvidenceResult, string> = {
  pass: "border-emerald-500/30 bg-emerald-500/12 text-emerald-700 dark:text-emerald-300",
  fail: "border-destructive/30 bg-destructive/10 text-foreground",
  partial: "border-amber-500/30 bg-amber-500/12 text-amber-700 dark:text-amber-300",
  unknown: "border-border/80 bg-muted/70 text-muted-foreground",
};

function buildEvidencePayload(item: EvidenceItem): Record<string, unknown> {
  if (!item.storageRef) {
    return {
      sourceRefType: item.sourceRefType,
      sourceRefId: item.sourceRefId,
    };
  }

  try {
    const parsed = JSON.parse(item.storageRef) as Record<string, unknown>;
    return parsed;
  } catch {
    return {
      storageRef: item.storageRef,
      sourceRefType: item.sourceRefType,
      sourceRefId: item.sourceRefId,
    };
  }
}

export function EvidenceItemCard({ item }: EvidenceItemCardProps) {
  const [open, setOpen] = useState(false);
  const payload = useMemo(() => buildEvidencePayload(item), [item]);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <Card className="rounded-[1.5rem] border-border/70 bg-card/80">
        <CardHeader className="p-0">
          <CollapsibleTrigger
            aria-expanded={open}
            className="flex w-full items-center justify-between gap-4 rounded-[1.5rem] p-5 text-left"
          >
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium">{EVIDENCE_TYPE_LABELS[item.evidenceType]}</p>
                <Badge className={cn("border", resultClasses[item.result])} variant={item.result === "fail" ? "destructive" : "outline"}>
                  {item.result}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">
                Collected {format(new Date(item.createdAt), "MMM d, yyyy 'at' HH:mm")}
              </p>
            </div>
            {open ? (
              <ChevronUp className="h-4 w-4 shrink-0 text-muted-foreground" />
            ) : (
              <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
            )}
          </CollapsibleTrigger>
        </CardHeader>
        <CollapsibleContent>
          <CardContent className="space-y-4 p-5 pt-0">
            <div className="rounded-2xl border border-border/60 bg-background/70 p-4">
              <p className="text-sm font-medium">Summary</p>
              <p className="mt-2 text-sm text-muted-foreground">
                {item.summary ?? "No summary available for this evidence item."}
              </p>
            </div>
            {item.storageRef ? (
              <div className="space-y-2">
                <p className="text-sm font-medium">Supporting data</p>
                <JsonViewer maxDepth={2} value={payload} />
              </div>
            ) : null}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}
