"use client";

import { useState } from "react";
import { CheckCircle2, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";

interface RecoveryCodesStepProps {
  onComplete: () => void;
  pulseAcknowledge?: boolean;
  recoveryCodes: string[];
}

export function RecoveryCodesStep({
  onComplete,
  pulseAcknowledge = false,
  recoveryCodes,
}: RecoveryCodesStepProps) {
  const [acknowledged, setAcknowledged] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(recoveryCodes.join("\n"));
    setCopied(true);
    window.setTimeout(() => {
      setCopied(false);
    }, 1500);
  };

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          Recovery codes
        </p>
        <h2 className="text-2xl font-semibold tracking-tight">
          Save your recovery codes
        </h2>
        <p className="text-sm text-muted-foreground">
          Store these codes somewhere safe. Each code can only be used once.
        </p>
      </div>

      <div className="rounded-2xl border border-border/70 bg-muted/35 p-4">
        <div className="grid gap-2 sm:grid-cols-2">
          {recoveryCodes.map((code) => (
            <code
              key={code}
              className="rounded-lg bg-background px-3 py-2 font-mono text-sm"
            >
              {code}
            </code>
          ))}
        </div>
      </div>

      <Button onClick={() => void handleCopy()} type="button" variant="outline">
        {copied ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
        {copied ? "Copied!" : "Copy all codes"}
      </Button>

      <div
        className={`rounded-2xl border border-border/70 bg-card/70 p-4 transition ${
          pulseAcknowledge ? "animate-pulse border-brand-accent" : ""
        }`}
      >
        <div className="flex items-start gap-3">
          <Checkbox
            checked={acknowledged}
            id="recovery-codes-acknowledgement"
            onChange={(event) => {
              setAcknowledged(event.target.checked);
            }}
          />
          <Label
            className="leading-6"
            htmlFor="recovery-codes-acknowledgement"
          >
            I have saved my recovery codes in a safe place
          </Label>
        </div>
      </div>

      <Button
        className="w-full"
        disabled={!acknowledged}
        onClick={onComplete}
        type="button"
      >
        Complete setup
      </Button>
    </div>
  );
}
