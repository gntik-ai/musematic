"use client";

import { Compass, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface OnboardingStepTourProps {
  isPending: boolean;
  onFinish: () => void;
}

export function OnboardingStepTour({ isPending, onFinish }: OnboardingStepTourProps) {
  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          Product tour
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">Review the main shell</h1>
        <p className="text-sm text-muted-foreground">
          The dashboard, marketplace, workspaces, and settings are ready.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {["Dashboard", "Marketplace", "Workspaces", "Settings"].map((item) => (
          <div key={item} className="flex items-center gap-3 rounded-md border border-border/70 p-3">
            <Compass className="h-4 w-4 text-brand-accent" />
            <span className="text-sm font-medium">{item}</span>
          </div>
        ))}
      </div>
      <Button className="w-full" disabled={isPending} type="button" onClick={onFinish}>
        {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
        Finish onboarding
      </Button>
    </div>
  );
}
