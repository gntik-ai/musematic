"use client";

import { useEffect } from "react";
import { Copy, Loader2 } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMfaEnrollMutation } from "@/lib/hooks/use-auth-mutations";
import { toast } from "@/lib/hooks/use-toast";

interface QrCodeStepProps {
  allowSkip?: boolean;
  onNext: () => void;
  onSkip?: () => void;
}

export function QrCodeStep({
  allowSkip = false,
  onNext,
  onSkip,
}: QrCodeStepProps) {
  const enrollMutation = useMfaEnrollMutation();
  const { data, isError, isPending, mutate, status } = enrollMutation;

  useEffect(() => {
    if (status === "idle") {
      mutate();
    }
  }, [mutate, status]);

  const handleCopy = async () => {
    if (!data?.secret_key) {
      return;
    }

    await navigator.clipboard.writeText(data.secret_key);
    toast({
      title: "Secret key copied",
      variant: "success",
    });
  };

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          MFA enrollment
        </p>
        <h2 className="text-2xl font-semibold tracking-tight">
          Set up authenticator
        </h2>
        <p className="text-sm text-muted-foreground">
          Scan this QR code with your authenticator app. If you can&apos;t scan it,
          use the secret key below instead.
        </p>
      </div>

      {isPending ? (
        <div className="space-y-4">
          <Skeleton className="mx-auto h-52 w-52 rounded-2xl" />
          <Skeleton className="h-12 w-full rounded-xl" />
        </div>
      ) : null}

      {isError ? (
        <div className="rounded-xl border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          Unable to load MFA enrollment details. Please try again.
        </div>
      ) : null}

      {data ? (
        <div className="space-y-4">
          <div className="mx-auto flex w-fit items-center justify-center rounded-3xl border border-border/70 bg-card p-5">
            <QRCodeSVG
              size={200}
              value={data.provisioning_uri}
            />
          </div>
          <div className="space-y-2 rounded-2xl border border-border/70 bg-muted/35 p-4">
            <p className="text-sm font-medium">Can&apos;t scan? Enter this code manually:</p>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <code className="rounded-lg bg-background px-3 py-2 font-mono text-sm">
                {data.secret_key}
              </code>
              <Button onClick={() => void handleCopy()} type="button" variant="outline">
                <Copy className="h-4 w-4" />
                Copy
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
        {allowSkip && onSkip ? (
          <Button onClick={onSkip} type="button" variant="ghost">
            Skip for now
          </Button>
        ) : null}
        <Button
          disabled={!data || isPending}
          onClick={onNext}
          type="button"
        >
          {isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading
            </>
          ) : (
            "Next"
          )}
        </Button>
      </div>
    </div>
  );
}
