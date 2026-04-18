"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import {
  decodeOAuthSessionFragment,
  isOAuthCallbackMfaResponse,
  toAuthSession,
  toAuthSessionFromOAuthCallback,
  type LoginSuccessResponse,
  type MfaVerifyResponse,
} from "@/lib/api/auth";
import { OAuthProviderButtons } from "@/components/features/auth/OAuthProviderButtons";
import { LoginForm } from "@/components/features/auth/login-form/LoginForm";
import { LockoutMessage } from "@/components/features/auth/login-form/LockoutMessage";
import { MfaChallengeForm } from "@/components/features/auth/login-form/MfaChallengeForm";
import { Button } from "@/components/ui/button";
import { toast } from "@/lib/hooks/use-toast";
import { useAuthStore } from "@/store/auth-store";

type LoginFlowState =
  | { step: "credentials" }
  | { step: "mfa_challenge"; sessionToken: string }
  | { step: "locked"; unlockAt: Date }
  | { step: "success" };

function getRedirectTarget(redirectTo: string | null): string {
  if (!redirectTo) {
    return "/home";
  }

  if (!redirectTo.startsWith("/") || redirectTo.startsWith("//")) {
    return "/home";
  }

  return redirectTo;
}

function getOAuthErrorMessage(errorCode: string | null): string | null {
  switch (errorCode) {
    case "invalid_oauth_callback":
      return "The OAuth callback was incomplete. Please try again.";
    case "oauth_state_invalid":
      return "The OAuth sign-in request was invalid or tampered with.";
    case "oauth_state_expired":
      return "The OAuth sign-in request expired. Please try again.";
    case "oauth_provider_disabled":
      return "This OAuth provider is currently disabled.";
    case "oauth_link_conflict":
      return "An account with this email already exists. Sign in locally first and then link the provider.";
    default:
      return errorCode ? "OAuth sign-in failed. Please try again." : null;
  }
}

function LoginPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const setAuth = useAuthStore((state) => state.setAuth);
  const [state, setState] = useState<LoginFlowState>({ step: "credentials" });
  const errorCode = searchParams.get("error");
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

  useEffect(() => {
    const description = getOAuthErrorMessage(errorCode);
    if (!description) {
      return;
    }

    toast({
      description,
      title: "OAuth sign-in failed",
      variant: "destructive",
    });
  }, [errorCode]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const hashParams = new URLSearchParams(window.location.hash.slice(1));
    const encodedSession = hashParams.get("oauth_session");
    if (!encodedSession) {
      return;
    }

    try {
      const payload = decodeOAuthSessionFragment(encodedSession);
      window.history.replaceState({}, "", window.location.pathname + window.location.search);

      if (isOAuthCallbackMfaResponse(payload)) {
        setState({
          step: "mfa_challenge",
          sessionToken: payload.session_token,
        });
        toast({
          title: "Complete MFA to finish OAuth sign-in.",
        });
        return;
      }

      setAuth(toAuthSessionFromOAuthCallback(payload));
      setState({ step: "success" });
      router.push(redirectTarget);
    } catch {
      window.history.replaceState({}, "", window.location.pathname + window.location.search);
      toast({
        title: "OAuth sign-in could not be completed",
        variant: "destructive",
      });
    }
  }, [redirectTarget, router, setAuth]);

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
        <>
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
          <OAuthProviderButtons />
        </>
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

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="space-y-6" />}>
      <LoginPageContent />
    </Suspense>
  );
}
