"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Copy, Loader2 } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { useTenantSetupMutations } from "@/lib/hooks/use-tenant-setup";

type SetupMutations = ReturnType<typeof useTenantSetupMutations>;

interface MandatoryMfaStepProps {
  mutations: Pick<SetupMutations, "mfaStart" | "mfaVerify">;
  onComplete: () => void;
}

export function MandatoryMfaStep({ mutations, onComplete }: MandatoryMfaStepProps) {
  const [code, setCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [acknowledged, setAcknowledged] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasRecoveryCodes = recoveryCodes.length > 0;

  useEffect(() => {
    if (mutations.mfaStart.status === "idle") {
      mutations.mfaStart.mutate(undefined);
    }
  }, [mutations.mfaStart]);

  async function verifyCode() {
    if (code.trim().length < 6 || mutations.mfaVerify.isPending) {
      return;
    }
    setError(null);
    try {
      const response = await mutations.mfaVerify.mutateAsync({
        totp_code: code.trim(),
      });
      setRecoveryCodes(response.recovery_codes);
    } catch {
      setCode("");
      setError("The code could not be verified.");
    }
  }

  async function copyRecoveryCodes() {
    await navigator.clipboard.writeText(recoveryCodes.join("\n"));
    setCopied(true);
    window.setTimeout(() => {
      setCopied(false);
    }, 1500);
  }

  if (hasRecoveryCodes) {
    return (
      <div className="space-y-6">
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
            Recovery codes
          </p>
          <h2 className="text-2xl font-semibold tracking-tight">Save your recovery codes</h2>
          <p className="text-sm text-muted-foreground">
            These codes are shown once. Store them before continuing.
          </p>
        </div>
        <div className="grid gap-2 rounded-md border border-border/70 bg-muted/35 p-4 sm:grid-cols-2">
          {recoveryCodes.map((recoveryCode) => (
            <code key={recoveryCode} className="rounded bg-background px-3 py-2 font-mono text-sm">
              {recoveryCode}
            </code>
          ))}
        </div>
        <Button type="button" variant="outline" onClick={() => void copyRecoveryCodes()}>
          {copied ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
          {copied ? "Copied" : "Copy codes"}
        </Button>
        <div className="flex items-start gap-3 rounded-md border border-border/70 bg-card/70 p-4">
          <Checkbox
            checked={acknowledged}
            id="tenant-setup-recovery-ack"
            onChange={(event) => setAcknowledged(event.currentTarget.checked)}
          />
          <Label className="leading-6" htmlFor="tenant-setup-recovery-ack">
            I have saved these recovery codes
          </Label>
        </div>
        <Button className="w-full" disabled={!acknowledged} type="button" onClick={onComplete}>
          Continue
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          Mandatory MFA
        </p>
        <h2 className="text-2xl font-semibold tracking-tight">Set up authenticator</h2>
        <p className="text-sm text-muted-foreground">
          Scan the QR code, then enter a 6-digit authenticator code.
        </p>
      </div>

      {mutations.mfaStart.isPending ? (
        <div className="flex h-52 items-center justify-center rounded-md border border-border/70">
          <Loader2 className="h-5 w-5 animate-spin text-brand-accent" />
        </div>
      ) : null}

      {mutations.mfaStart.data ? (
        <div className="space-y-4">
          <div className="mx-auto flex w-fit max-w-full items-center justify-center overflow-hidden rounded-md border border-border/70 bg-card p-5">
            <QRCodeSVG
              className="block h-auto max-w-full"
              size={200}
              value={mutations.mfaStart.data.provisioning_uri}
            />
          </div>
          <div className="rounded-md border border-border/70 bg-muted/35 p-4">
            <p className="text-sm font-medium">Manual key</p>
            <code className="mt-2 block break-all rounded bg-background px-3 py-2 font-mono text-sm">
              {mutations.mfaStart.data.totp_secret}
            </code>
          </div>
        </div>
      ) : null}

      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          void verifyCode();
        }}
      >
        <Input
          autoComplete="one-time-code"
          inputMode="numeric"
          maxLength={6}
          placeholder="000000"
          value={code}
          onChange={(event) => setCode(event.currentTarget.value.replace(/\D/g, ""))}
        />
        {error ? (
          <div className="rounded-md border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        ) : null}
        <Button
          className="w-full"
          disabled={!mutations.mfaStart.data || code.length < 6 || mutations.mfaVerify.isPending}
          type="submit"
        >
          {mutations.mfaVerify.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          Verify MFA
        </Button>
      </form>
    </div>
  );
}
