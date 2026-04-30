"use client";

import { useState } from "react";
import { CheckCircle2, PlugZap } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { SlackWizardSteps } from "./SlackWizardSteps";
import { EmailWizardSteps } from "./EmailWizardSteps";
import { TelegramWizardSteps } from "./TelegramWizardSteps";
import { WebhookWizardSteps } from "./WebhookWizardSteps";

const steps = ["Prerequisites", "Credentials", "Test connectivity", "Scope", "Activate"] as const;
const connectorTypes = ["slack", "telegram", "email", "webhook"] as const;

function ConnectorSpecificSteps({ type }: { type: (typeof connectorTypes)[number] }) {
  switch (type) {
    case "slack":
      return <SlackWizardSteps />;
    case "telegram":
      return <TelegramWizardSteps />;
    case "email":
      return <EmailWizardSteps />;
    case "webhook":
      return <WebhookWizardSteps />;
  }
}

export function ConnectorSetupWizard() {
  const [open, setOpen] = useState(false);
  const [type, setType] = useState<(typeof connectorTypes)[number]>("slack");
  const [stepIndex, setStepIndex] = useState(0);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <PlugZap className="h-4 w-4" />
          Add connector
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Connector setup</DialogTitle>
          <DialogDescription>
            Guided setup validates credentials with dry-run connectivity checks before activation.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-5">
          <div className="grid gap-2 md:grid-cols-5">
            {steps.map((step, index) => (
              <Badge
                key={step}
                className="justify-center"
                variant={index === stepIndex ? "default" : "outline"}
              >
                {index < stepIndex ? <CheckCircle2 className="mr-1 h-3 w-3" /> : null}
                {step}
              </Badge>
            ))}
          </div>
          <Select
            className="w-full md:w-64"
            value={type}
            onChange={(event) => setType(event.target.value as (typeof connectorTypes)[number])}
          >
            {connectorTypes.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </Select>
          <ConnectorSpecificSteps type={type} />
          <div className="rounded-md border p-3 text-sm text-muted-foreground">
            Step {stepIndex + 1}: {steps[stepIndex]}. Connectivity tests call the connector dry-run endpoint and do not create delivery records.
          </div>
          <div className="flex justify-between">
            <Button disabled={stepIndex === 0} onClick={() => setStepIndex((value) => Math.max(0, value - 1))} variant="outline">
              Back
            </Button>
            <Button onClick={() => setStepIndex((value) => Math.min(steps.length - 1, value + 1))}>
              {stepIndex === steps.length - 1 ? "Ready" : "Next"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
