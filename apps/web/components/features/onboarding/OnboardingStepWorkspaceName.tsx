"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface OnboardingStepWorkspaceNameProps {
  defaultName: string;
  isPending: boolean;
  onSubmit: (workspaceName: string) => void;
}

export function OnboardingStepWorkspaceName({
  defaultName,
  isPending,
  onSubmit,
}: OnboardingStepWorkspaceNameProps) {
  const [workspaceName, setWorkspaceName] = useState(defaultName);

  return (
    <form
      className="space-y-5"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(workspaceName);
      }}
    >
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          Workspace
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">Name your workspace</h1>
        <p className="text-sm text-muted-foreground">
          This is the default workspace created with your account.
        </p>
      </div>
      <Input
        autoFocus
        value={workspaceName}
        onChange={(event) => setWorkspaceName(event.currentTarget.value)}
      />
      <Button className="w-full" disabled={!workspaceName.trim() || isPending} type="submit">
        {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
        Continue
      </Button>
    </form>
  );
}
