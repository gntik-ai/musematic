"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, RefreshCcw } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import { useReactCycles } from "@/lib/hooks/use-react-cycles";
import type { ReactCycle } from "@/types/trajectory";

export interface ReactCycleViewerProps {
  executionId: string;
}

function CycleSection({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="flex w-full items-center justify-between rounded-xl border border-border/60 bg-muted/30 px-4 py-3 text-left text-sm font-medium">
        <span>{label}</span>
        {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="rounded-b-xl border border-t-0 border-border/60 bg-background/70 px-4 py-3 text-sm text-muted-foreground">
          {value || "Not captured for this cycle."}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function ReactCycleCard({ cycle }: { cycle: ReactCycle }) {
  return (
    <div className="rounded-2xl border border-border/60 bg-background/80 p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-medium">Cycle {cycle.index}</p>
          <p className="text-sm text-muted-foreground">{cycle.durationMs}ms</p>
        </div>
        <p className="rounded-full border border-border/60 bg-muted/50 px-3 py-1 text-xs text-muted-foreground">
          Tool: {cycle.action.tool || "n/a"}
        </p>
      </div>
      <div className="mt-4 space-y-3">
        <CycleSection label="Thought" value={cycle.thought} />
        <CycleSection
          label="Action"
          value={cycle.action.tool ? `${cycle.action.tool}
${JSON.stringify(cycle.action.args, null, 2)}` : ""}
        />
        <CycleSection label="Observation" value={cycle.observation} />
      </div>
    </div>
  );
}

export function ReactCycleViewer({ executionId }: ReactCycleViewerProps) {
  const reactCyclesQuery = useReactCycles(executionId);
  const cycles = reactCyclesQuery.data ?? [];

  return (
    <Card className="rounded-[1.75rem]">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <RefreshCcw className="h-5 w-5 text-brand-accent" />
          ReAct cycles
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Step through Thought, Action, and Observation tuples for this execution.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {reactCyclesQuery.isLoading ? (
          Array.from({ length: 2 }).map((_, index) => (
            <Skeleton key={index} className="h-56 rounded-2xl" />
          ))
        ) : cycles.length === 0 ? (
          <EmptyState
            description="No ReAct cycles were captured for this execution."
            title="ReAct trace unavailable"
          />
        ) : (
          <div className="space-y-4">
            {cycles.map((cycle) => (
              <ReactCycleCard key={cycle.index} cycle={cycle} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
