"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import {
  decodeOAuthSessionFragment,
  isOAuthCallbackMfaResponse,
  toAuthSessionFromOAuthCallback,
} from "@/lib/api/auth";
import { useAuthStore } from "@/store/auth-store";

interface OAuthCallbackHandlerProps {
  provider: string;
}

type CallbackState = "loading" | "success" | "error";

export function OAuthCallbackHandler({ provider }: OAuthCallbackHandlerProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const setAuth = useAuthStore((state) => state.setAuth);
  const [state, setState] = useState<CallbackState>("loading");
  const [message, setMessage] = useState("Completing OAuth sign-in");

  useEffect(() => {
    const error = searchParams.get("error");
    if (error) {
      window.history.replaceState(null, "", window.location.pathname);
      setState("error");
      setMessage(error.replaceAll("_", " "));
      return;
    }

    const hashParams = new URLSearchParams(window.location.hash.slice(1));
    const encodedSession = hashParams.get("oauth_session");
    window.history.replaceState(null, "", window.location.pathname);

    if (!encodedSession) {
      setState("error");
      setMessage("OAuth callback did not include a session payload.");
      return;
    }

    try {
      const payload = decodeOAuthSessionFragment(encodedSession);
      if (isOAuthCallbackMfaResponse(payload)) {
        router.replace(`/login/mfa?session_token=${encodeURIComponent(payload.session_token)}`);
        return;
      }

      setAuth(toAuthSessionFromOAuthCallback(payload));
      setState("success");
      const status = payload.user.status;
      if (status === "pending_profile_completion") {
        router.replace("/profile-completion");
      } else if (status === "pending_approval") {
        router.replace("/waiting-approval");
      } else {
        router.replace("/home");
      }
    } catch {
      setState("error");
      setMessage("OAuth sign-in could not be completed.");
    }
  }, [provider, router, searchParams, setAuth]);

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          {provider} OAuth
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">
          {state === "error" ? "Sign-in failed" : "Finishing sign-in"}
        </h1>
        <p className="text-sm text-muted-foreground">{message}</p>
      </div>
      {state === "loading" ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <Loader2 className="h-4 w-4 animate-spin" />
          Processing secure callback
        </div>
      ) : null}
    </div>
  );
}
