"use client";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function SlackWizardSteps() {
  return (
    <div className="space-y-3">
      <Alert>
        <AlertTitle>Slack prerequisites</AlertTitle>
        <AlertDescription>Use a bot token with auth.test access and a signing secret.</AlertDescription>
      </Alert>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-2"><Label>Team ID</Label><Input placeholder="T123" /></div>
        <div className="space-y-2"><Label>Bot token secret ref</Label><Input placeholder="bot_token" /></div>
      </div>
    </div>
  );
}
