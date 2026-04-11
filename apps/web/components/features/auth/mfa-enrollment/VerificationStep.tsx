"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { InputOTP } from "@/components/ui/input-otp";
import { useMfaConfirmMutation } from "@/lib/hooks/use-auth-mutations";
import { ApiError } from "@/types/api";

interface VerificationStepProps {
  onBack: () => void;
  onSuccess: (recoveryCodes: string[]) => void;
}

export function VerificationStep({
  onBack,
  onSuccess,
}: VerificationStepProps) {
  const [code, setCode] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const { isPending, mutateAsync } = useMfaConfirmMutation();
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const submit = useCallback(
    async (value: string) => {
      if (value.length < 6 || isPending) {
        return;
      }

      setErrorMessage(null);

      try {
        const response = await mutateAsync({ code: value });
        onSuccess(response.recovery_codes);
      } catch (error) {
        if (error instanceof ApiError && error.code === "INVALID_CODE") {
          setCode("");
          setErrorMessage("Incorrect code. Please try again.");
          inputRef.current?.focus();
          return;
        }

        setErrorMessage("Unable to verify your setup right now.");
      }
    },
    [isPending, mutateAsync, onSuccess],
  );

  useEffect(() => {
    if (code.length === 6) {
      void submit(code);
    }
  }, [code, submit]);

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          Verify setup
        </p>
        <h2 className="text-2xl font-semibold tracking-tight">
          Confirm your authenticator
        </h2>
        <p className="text-sm text-muted-foreground">
          Enter the 6-digit code from your authenticator app to confirm setup.
        </p>
      </div>

      <form
        className="space-y-5"
        onSubmit={(event) => {
          event.preventDefault();
          void submit(code);
        }}
      >
        <InputOTP
          ref={inputRef}
          aria-label="Authenticator verification code"
          inputMode="numeric"
          maxLength={6}
          onChange={setCode}
          placeholder="000000"
          value={code}
        />
        {errorMessage ? (
          <div className="rounded-xl border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {errorMessage}
          </div>
        ) : null}
        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
          <Button onClick={onBack} type="button" variant="ghost">
            Back
          </Button>
          <Button
            disabled={isPending || code.length < 6}
            type="submit"
          >
            {isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Verifying
              </>
            ) : (
              "Verify"
            )}
          </Button>
        </div>
      </form>
    </div>
  );
}
