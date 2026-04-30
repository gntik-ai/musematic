"use client";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function EmailWizardSteps() {
  return (
    <div className="space-y-3">
      <Alert>
        <AlertTitle>Email prerequisites</AlertTitle>
        <AlertDescription>Configure IMAP and SMTP credentials; test uses IMAP NOOP.</AlertDescription>
      </Alert>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-2"><Label>IMAP host</Label><Input placeholder="imap.example.com" /></div>
        <div className="space-y-2"><Label>SMTP host</Label><Input placeholder="smtp.example.com" /></div>
      </div>
    </div>
  );
}
