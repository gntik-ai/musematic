"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, MessageSquareQuote } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import { useDebateTranscript } from "@/lib/hooks/use-debate-transcript";
import { cn } from "@/lib/utils";
import type { DebateTurn } from "@/types/trajectory";

export interface DebateTranscriptProps {
  executionId: string;
}

function bubbleClasses(position: DebateTurn["position"]): string {
  if (position === "support") {
    return "border-emerald-500/30 bg-emerald-500/10";
  }
  if (position === "oppose") {
    return "border-rose-500/30 bg-rose-500/10";
  }
  return "border-sky-500/30 bg-sky-500/10";
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Time unavailable";
  }
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function DebateTurnCard({ turn }: { turn: DebateTurn }) {
  const [open, setOpen] = useState(false);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className={cn("rounded-2xl border p-4 shadow-sm", bubbleClasses(turn.position))}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">{turn.position}</Badge>
              {turn.participantIsDeleted ? (
                <Badge className="border-border/70 bg-muted/70 text-muted-foreground" variant="outline">
                  Agent no longer exists
                </Badge>
              ) : null}
            </div>
            <p className="font-medium">{turn.participantDisplayName}</p>
            <p className="text-sm text-muted-foreground">{turn.participantAgentFqn}</p>
          </div>
          <span className="text-xs text-muted-foreground">{formatTimestamp(turn.timestamp)}</span>
        </div>
        <p className="mt-3 text-sm text-foreground">{turn.content}</p>
        <CollapsibleTrigger className="mt-4 flex items-center gap-2 text-sm font-medium text-brand-accent">
          {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          Reasoning trace
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="mt-3 rounded-xl border border-border/50 bg-background/70 p-3 text-sm text-muted-foreground">
            <p className="font-medium text-foreground">Reference: {turn.reasoningTraceId ?? "n/a"}</p>
            <p className="mt-2">{turn.content}</p>
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

export function DebateTranscript({ executionId }: DebateTranscriptProps) {
  const transcriptQuery = useDebateTranscript(executionId);
  const turns = transcriptQuery.data ?? [];

  return (
    <Card className="rounded-[1.75rem]">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MessageSquareQuote className="h-5 w-5 text-brand-accent" />
          Debate transcript
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Participant-colored transcript reconstructed from structured reasoning traces.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {transcriptQuery.isLoading ? (
          Array.from({ length: 2 }).map((_, index) => (
            <Skeleton key={index} className="h-40 rounded-2xl" />
          ))
        ) : turns.length === 0 ? (
          <EmptyState
            description="No debate turns were captured for this execution."
            title="Debate transcript unavailable"
          />
        ) : (
          <div className="space-y-4">
            {turns.map((turn, index) => (
              <DebateTurnCard key={`${turn.participantAgentFqn}-${turn.timestamp}-${index}`} turn={turn} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
