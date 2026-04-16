"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Badge } from "@/components/ui/badge";
import {
  REASONING_MODE_LABELS,
  type ReasoningTraceStep as ReasoningTraceStepModel,
} from "@/lib/types/operator-dashboard";

export interface ReasoningTraceStepProps {
  step: ReasoningTraceStepModel;
  stepNumber: number;
}

export function ReasoningTraceStep({
  step,
  stepNumber,
}: ReasoningTraceStepProps) {
  const [open, setOpen] = useState(false);
  const [showFullOutput, setShowFullOutput] = useState(false);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className="rounded-xl border border-border/60 bg-background/70">
        <CollapsibleTrigger
          aria-expanded={open}
          className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
        >
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">Step {stepNumber}</Badge>
              <Badge variant="outline">{REASONING_MODE_LABELS[step.mode]}</Badge>
              <span className="text-sm text-muted-foreground">
                {step.tokenCount} tokens
              </span>
              <span className="text-sm text-muted-foreground">
                {step.durationMs}ms
              </span>
              {step.selfCorrections.length > 0 ? (
                <Badge
                  className="border-amber-500/30 bg-amber-500/12 text-amber-700 dark:text-amber-300"
                  variant="outline"
                >
                  {step.selfCorrections.length} corrections
                </Badge>
              ) : null}
            </div>
            <p className="text-sm text-foreground">{step.inputSummary}</p>
          </div>
          {open ? (
            <ChevronUp className="h-4 w-4 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
          )}
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="space-y-4 border-t border-border/60 px-4 py-4 text-sm">
            <div className="space-y-1">
              <p className="font-medium">Input summary</p>
              <p className="text-muted-foreground">{step.inputSummary}</p>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <p className="font-medium">Output summary</p>
                {step.fullOutputRef ? (
                  <button
                    className="text-sm font-medium text-brand-accent"
                    type="button"
                    onClick={() => setShowFullOutput((value) => !value)}
                  >
                    {showFullOutput ? "Hide full output" : "Show full output"}
                  </button>
                ) : null}
              </div>
              <p className="text-muted-foreground">{step.outputSummary}</p>
              {showFullOutput && step.fullOutputRef ? (
                <pre className="overflow-x-auto rounded-lg border border-border/60 bg-muted/50 p-3 text-xs">
                  {step.fullOutputRef}
                </pre>
              ) : null}
            </div>

            {step.selfCorrections.length > 0 ? (
              <div className="space-y-3">
                <p className="font-medium">Self-correction chain</p>
                {step.selfCorrections.map((iteration) => (
                  <div
                    key={`${step.id}-${iteration.iterationIndex}`}
                    className="rounded-lg border border-border/60 bg-muted/40 p-3"
                  >
                    <p className="text-sm font-medium">
                      Iteration {iteration.iterationIndex}
                    </p>
                    <p className="mt-2 text-muted-foreground">
                      {iteration.originalOutputSummary}
                    </p>
                    <p className="mt-2 text-sm font-medium">Reason</p>
                    <p className="text-muted-foreground">
                      {iteration.correctionReason}
                    </p>
                    <p className="mt-2 text-sm font-medium">Corrected output</p>
                    <p className="text-muted-foreground">
                      {iteration.correctedOutputSummary}
                    </p>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}
