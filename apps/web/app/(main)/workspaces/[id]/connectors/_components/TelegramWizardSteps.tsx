"use client";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function TelegramWizardSteps() {
  return (
    <div className="space-y-3">
      <Alert>
        <AlertTitle>Telegram prerequisites</AlertTitle>
        <AlertDescription>Use a bot token that can answer Telegram getMe.</AlertDescription>
      </Alert>
      <div className="space-y-2">
        <Label>Bot token secret ref</Label>
        <Input placeholder="bot_token" />
      </div>
    </div>
  );
}
