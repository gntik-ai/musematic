"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  useResendVerificationMutation,
  useVerifyEmailMutation,
} from "@/lib/hooks/use-auth-mutations";

type VerifyState = "loading" | "success" | "expired" | "missing";

function VerifyEmailContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = useMemo(() => searchParams.get("token"), [searchParams]);
  const verifyMutation = useVerifyEmailMutation();
  const resendMutation = useResendVerificationMutation();
  const [state, setState] = useState<VerifyState>("loading");
  const [email, setEmail] = useState("");

  useEffect(() => {
    if (!token) {
      setState("missing");
      return;
    }
    verifyMutation
      .mutateAsync(token)
      .then((response) => {
        setState("success");
        window.setTimeout(() => {
          router.replace(
            response.status === "pending_approval" ? "/waiting-approval" : "/login",
          );
        }, 3000);
      })
      .catch(() => {
        setState("expired");
      });
  }, [router, token]);

  if (state === "loading") {
    return (
      <div className="space-y-4">
        <Loader2 className="h-5 w-5 animate-spin text-brand-accent" />
        <h1 className="text-3xl font-semibold tracking-tight">Verifying email</h1>
      </div>
    );
  }

  if (state === "success") {
    return (
      <div className="space-y-4">
        <h1 className="text-3xl font-semibold tracking-tight">Email verified</h1>
        <p className="text-sm text-muted-foreground">Redirecting to your next step.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          Verification issue
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">
          {state === "missing" ? "Verification token missing" : "Verification link expired"}
        </h1>
        <p className="text-sm text-muted-foreground">
          Request a fresh verification link for your account email.
        </p>
      </div>
      <div className="space-y-3">
        <Input
          autoComplete="email"
          placeholder="name@company.com"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.currentTarget.value)}
        />
        <Button
          className="w-full"
          disabled={!email || resendMutation.isPending}
          type="button"
          onClick={() => {
            void resendMutation.mutateAsync(email);
          }}
        >
          Resend verification
        </Button>
      </div>
      <Button asChild className="w-full" variant="outline">
        <Link href="/login">Back to login</Link>
      </Button>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<div className="space-y-6" />}>
      <VerifyEmailContent />
    </Suspense>
  );
}
