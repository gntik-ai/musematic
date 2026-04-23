"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, ShieldAlert, Wrench } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { DecisionRationale } from "@/types/goal";

interface DecisionRationalePanelProps {
  rationale: DecisionRationale | null;
}

interface SectionProps {
  title: string;
  count: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

function RationaleSection({
  children,
  count,
  defaultOpen = false,
  title,
}: SectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <Collapsible onOpenChange={setOpen} open={open}>
      <div className="rounded-2xl border border-border/70 bg-card/70">
        <CollapsibleTrigger
          aria-label={`Toggle ${title}`}
          className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left"
        >
          <div>
            <p className="text-sm font-semibold text-foreground">{title}</p>
            <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
              {count} items
            </p>
          </div>
          {open ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="border-t border-border/60 px-4 py-3">{children}</div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

export function DecisionRationalePanel({
  rationale,
}: DecisionRationalePanelProps) {
  if (!rationale) {
    return (
      <div className="rounded-2xl border border-dashed border-border/70 bg-muted/20 px-5 py-8 text-center">
        <ShieldAlert className="mx-auto h-8 w-8 text-muted-foreground" />
        <p className="mt-3 text-sm font-semibold text-foreground">
          No decision rationale recorded
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          This response does not yet have structured rationale data attached.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <RationaleSection
        count={rationale.toolChoices.length}
        defaultOpen
        title="Tool choices"
      >
        {rationale.toolChoices.length > 0 ? (
          <ul className="space-y-3">
            {rationale.toolChoices.map((choice) => (
              <li key={`${choice.tool}-${choice.reason}`} className="space-y-1">
                <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                  <Wrench className="h-4 w-4 text-brand-accent" />
                  {choice.tool}
                </div>
                <p className="text-sm text-muted-foreground">{choice.reason}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            No tool-choice evidence was recorded for this response.
          </p>
        )}
      </RationaleSection>
      <RationaleSection
        count={rationale.retrievedMemories.length}
        title="Retrieved memories"
      >
        {rationale.retrievedMemories.length > 0 ? (
          <ul className="space-y-3">
            {rationale.retrievedMemories.map((memory) => (
              <li key={memory.memoryId} className="space-y-1">
                <p className="text-sm font-medium text-foreground">
                  {memory.memoryId}
                </p>
                <p className="text-sm text-muted-foreground">{memory.excerpt}</p>
                <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                  Relevance {memory.relevanceScore.toFixed(2)}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            No retrieved-memory evidence was recorded for this response.
          </p>
        )}
      </RationaleSection>
      <RationaleSection count={rationale.riskFlags.length} title="Risk flags">
        {rationale.riskFlags.length > 0 ? (
          <ul className="space-y-3">
            {rationale.riskFlags.map((flag) => (
              <li key={`${flag.category}-${flag.note}`} className="space-y-1">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium text-foreground">
                    {flag.category}
                  </p>
                  <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                    {flag.severity}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground">{flag.note}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            No explicit risk flags were recorded for this response.
          </p>
        )}
      </RationaleSection>
      <RationaleSection count={rationale.policyChecks.length} title="Policy checks">
        {rationale.policyChecks.length > 0 ? (
          <ul className="space-y-3">
            {rationale.policyChecks.map((check) => (
              <li key={check.policyId} className="space-y-1">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium text-foreground">
                    {check.policyName}
                  </p>
                  <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                    {check.verdict}
                  </span>
                </div>
                <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                  {check.policyId}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            No policy-check evidence was recorded for this response.
          </p>
        )}
      </RationaleSection>
    </div>
  );
}
