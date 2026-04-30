"use client";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function WebhookWizardSteps() {
  return (
    <div className="space-y-3">
      <Alert>
        <AlertTitle>Webhook prerequisites</AlertTitle>
        <AlertDescription>Destination must accept HEAD requests before activation.</AlertDescription>
      </Alert>
      <div className="space-y-2">
        <Label>Destination URL</Label>
        <Input placeholder="https://hooks.example.com/workspace" />
      </div>
    </div>
  );
}
