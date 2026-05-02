"use client";

import { Bot, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface OnboardingStepFirstAgentProps {
  isPending: boolean;
  onCreate: () => void;
  onSkip: () => void;
}

export function OnboardingStepFirstAgent({
  isPending,
  onCreate,
  onSkip,
}: OnboardingStepFirstAgentProps) {
  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          First agent
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">Create your first agent</h1>
        <p className="text-sm text-muted-foreground">
          Start the agent flow now or keep onboarding moving.
        </p>
      </div>
      <div className="rounded-md border border-border/70 bg-muted/30 p-4">
        <Bot className="mb-3 h-5 w-5 text-brand-accent" />
        <p className="text-sm text-muted-foreground">
          The agent creation flow opens from the main shell after onboarding.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Button disabled={isPending} type="button" onClick={onCreate}>
          {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          Mark planned
        </Button>
        <Button disabled={isPending} type="button" variant="outline" onClick={onSkip}>
          Skip
        </Button>
      </div>
    </div>
  );
}
