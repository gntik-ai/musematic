"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { LoginForm } from "@/components/features/auth/login-form/LoginForm";
import { LockoutMessage } from "@/components/features/auth/login-form/LockoutMessage";
import { MfaChallengeForm } from "@/components/features/auth/login-form/MfaChallengeForm";
import { Button } from "@/components/ui/button";
import { toast } from "@/lib/hooks/use-toast";
import { toAuthSession, type LoginSuccessResponse, type MfaVerifyResponse } from "@/lib/api/auth";
import { useAuthStore } from "@/store/auth-store";

type LoginFlowState =
  | { step: "credentials" }
  | { step: "mfa_challenge"; sessionToken: string }
  | { step: "locked"; unlockAt: Date }
  | { step: "success" };

function getRedirectTarget(redirectTo: string | null): string {
  if (!redirectTo) {
    return "/dashboard";
  }

  if (!redirectTo.startsWith("/") || redirectTo.startsWith("//")) {
    return "/dashboard";
  }

  return redirectTo;
}

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const setAuth = useAuthStore((state) => state.setAuth);
  const [state, setState] = useState<LoginFlowState>({ step: "credentials" });
  const message = searchParams.get("message");

  const redirectTarget = useMemo(
    () => getRedirectTarget(searchParams.get("redirectTo")),
    [searchParams],
  );

  useEffect(() => {
    if (message === "password_updated") {
      toast({
        title: "Password updated. Please log in.",
        variant: "success",
      });
    }
  }, [message]);

  const completeAuth = (
    response: LoginSuccessResponse | MfaVerifyResponse,
    options?: { recoveryCodeConsumed?: boolean },
  ) => {
    setAuth(toAuthSession(response));
    setState({ step: "success" });

    if (options?.recoveryCodeConsumed) {
      toast({
        title: "One recovery code has been used.",
        variant: "success",
      });
    }

    router.push(redirectTarget);
  };

  return (
    <div className="space-y-6">
      {state.step === "credentials" ? (
        <LoginForm
          onLockout={(lockoutSeconds) => {
            setState({
              step: "locked",
              unlockAt: new Date(Date.now() + lockoutSeconds * 1000),
            });
          }}
          onMfaChallenge={(sessionToken) => {
            setState({ step: "mfa_challenge", sessionToken });
          }}
          onSuccess={(response) => {
            completeAuth(response);
          }}
        />
      ) : null}

      {state.step === "mfa_challenge" ? (
        <MfaChallengeForm
          onBack={() => {
            setState({ step: "credentials" });
          }}
          onSuccess={(response) => {
            completeAuth(response, {
              recoveryCodeConsumed: response.recovery_code_consumed === true,
            });
          }}
          sessionToken={state.sessionToken}
        />
      ) : null}

      {state.step === "locked" ? (
        <div className="space-y-6">
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
              Access paused
            </p>
            <h1 className="text-3xl font-semibold tracking-tight">
              Too many failed attempts
            </h1>
            <p className="text-sm text-muted-foreground">
              Your account is temporarily locked to protect the workspace.
            </p>
          </div>
          <LockoutMessage
            onExpired={() => {
              setState({ step: "credentials" });
            }}
            unlockAt={state.unlockAt}
          />
          <Button
            className="w-full"
            onClick={() => {
              setState({ step: "credentials" });
            }}
            type="button"
            variant="outline"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to login
          </Button>
        </div>
      ) : null}
    </div>
  );
}
