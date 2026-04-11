"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InputOTP } from "@/components/ui/input-otp";
import { useMfaVerifyMutation } from "@/lib/hooks/use-auth-mutations";
import type { MfaVerifyResponse } from "@/lib/api/auth";
import { ApiError } from "@/types/api";

interface MfaChallengeFormProps {
  onBack: () => void;
  onSuccess: (response: MfaVerifyResponse) => void;
  sessionToken: string;
}

export function MfaChallengeForm({
  onBack,
  onSuccess,
  sessionToken,
}: MfaChallengeFormProps) {
  const [code, setCode] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [useRecoveryCode, setUseRecoveryCode] = useState(false);
  const { isPending, mutateAsync } = useMfaVerifyMutation();
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, [useRecoveryCode]);

  const submit = useCallback(
    async (value: string) => {
      if (!value || isPending) {
        return;
      }

      setErrorMessage(null);

      try {
        const response = await mutateAsync({
          session_token: sessionToken,
          code: value,
          use_recovery_code: useRecoveryCode || undefined,
        });
        onSuccess(response);
      } catch (error) {
        if (error instanceof ApiError && error.code === "INVALID_CODE") {
          setCode("");
          setErrorMessage("Invalid verification code");
          inputRef.current?.focus();
          return;
        }

        setErrorMessage("Unable to verify your code. Please try again.");
      }
    },
    [isPending, mutateAsync, onSuccess, sessionToken, useRecoveryCode],
  );

  useEffect(() => {
    if (!useRecoveryCode && code.length === 6) {
      void submit(code);
    }
  }, [code, submit, useRecoveryCode]);

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          Two-factor authentication
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">
          Verify your sign-in
        </h1>
        <p className="text-sm text-muted-foreground">
          {useRecoveryCode
            ? "Enter one of your recovery codes to continue."
            : "Enter the 6-digit code from your authenticator app."}
        </p>
      </div>
      <form
        className="space-y-5"
        onSubmit={(event) => {
          event.preventDefault();
          void submit(code);
        }}
      >
        {useRecoveryCode ? (
          <Input
            ref={inputRef}
            aria-label="Recovery code"
            autoComplete="one-time-code"
            onChange={(event) => setCode(event.target.value)}
            placeholder="Enter a recovery code"
            value={code}
          />
        ) : (
          <InputOTP
            ref={inputRef}
            aria-label="Authenticator code"
            inputMode="numeric"
            maxLength={6}
            onChange={setCode}
            placeholder="000000"
            value={code}
          />
          )}
        {errorMessage ? (
          <div
            className="rounded-xl border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive"
            role="alert"
          >
            {errorMessage}
          </div>
        ) : null}
        <Button
          className="w-full"
          disabled={isPending || (!useRecoveryCode && code.length < 6) || (useRecoveryCode && code.length === 0)}
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
        <div className="flex items-center justify-between gap-4 text-sm">
          <button
            aria-label={useRecoveryCode ? "Use authenticator code" : "Use a recovery code instead"}
            className="font-medium text-brand-primary transition hover:text-brand-primary/80"
            onClick={() => {
              setCode("");
              setErrorMessage(null);
              setUseRecoveryCode((value) => !value);
            }}
            type="button"
          >
            {useRecoveryCode ? "Use authenticator code" : "Use a recovery code instead"}
          </button>
          <button
            className="text-muted-foreground transition hover:text-foreground"
            onClick={onBack}
            type="button"
          >
            Back to login
          </button>
        </div>
      </form>
    </div>
  );
}
