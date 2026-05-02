"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface OnboardingStepInvitationsProps {
  isPending: boolean;
  onSubmit: (emails: string[]) => void;
}

export function OnboardingStepInvitations({
  isPending,
  onSubmit,
}: OnboardingStepInvitationsProps) {
  const [value, setValue] = useState("");

  return (
    <form
      className="space-y-5"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(parseEmails(value));
      }}
    >
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          Team
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">Invite teammates</h1>
        <p className="text-sm text-muted-foreground">
          Add one email per line, or skip this step.
        </p>
      </div>
      <Textarea
        placeholder={"alex@example.com\nsam@example.com"}
        value={value}
        onChange={(event) => setValue(event.currentTarget.value)}
      />
      <div className="grid gap-3 sm:grid-cols-2">
        <Button disabled={isPending} type="submit">
          {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          Send
        </Button>
        <Button disabled={isPending} type="button" variant="outline" onClick={() => onSubmit([])}>
          Skip
        </Button>
      </div>
    </form>
  );
}

function parseEmails(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((email) => email.trim().toLowerCase())
    .filter(Boolean);
}
