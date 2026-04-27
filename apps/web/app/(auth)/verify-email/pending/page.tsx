"use client";

import { Suspense, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Loader2, Send } from "lucide-react";
import { EmailVerificationStatus } from "@/components/features/auth/EmailVerificationStatus";
import { Button } from "@/components/ui/button";
import { useResendVerificationMutation } from "@/lib/hooks/use-auth-mutations";

function PendingVerificationContent() {
  const searchParams = useSearchParams();
  const email = useMemo(() => searchParams.get("email") ?? "", [searchParams]);
  const resendMutation = useResendVerificationMutation();
  const [lastSentAt, setLastSentAt] = useState<number | null>(null);
  const canResend = lastSentAt === null || Date.now() - lastSentAt > 60_000;

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          Verify email
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">Check your inbox</h1>
        <p className="text-sm text-muted-foreground">
          Use the verification link before signing in.
        </p>
      </div>
      <EmailVerificationStatus email={email} />
      <Button
        className="w-full"
        disabled={!email || !canResend || resendMutation.isPending}
        type="button"
        variant="outline"
        onClick={async () => {
          await resendMutation.mutateAsync(email);
          setLastSentAt(Date.now());
        }}
      >
        {resendMutation.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Send className="h-4 w-4" />
        )}
        Resend verification
      </Button>
      <div className="text-center text-sm">
        <Link className="font-medium text-brand-primary" href="/login">
          Back to login
        </Link>
      </div>
    </div>
  );
}

export default function PendingVerificationPage() {
  return (
    <Suspense fallback={<div className="space-y-6" />}>
      <PendingVerificationContent />
    </Suspense>
  );
}
