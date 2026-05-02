"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { createApiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const invitationApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

interface CrossTenantInvitationAcceptProps {
  email: string;
  token: string;
}

export function CrossTenantInvitationAccept({
  email,
  token,
}: CrossTenantInvitationAcceptProps) {
  const [displayName, setDisplayName] = useState(email.split("@", 1)[0] ?? "");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function acceptInvitation() {
    setPending(true);
    setError(null);
    try {
      await invitationApi.post(
        `/api/v1/accounts/invitations/${encodeURIComponent(token)}/accept`,
        {
          display_name: displayName,
          password,
          token,
        },
        { skipAuth: false, skipRetry: true },
      );
      window.location.assign("/login?message=invitation_accepted");
    } catch (acceptError) {
      setError(acceptError instanceof Error ? acceptError.message : "Unable to accept invite.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      className="space-y-5"
      onSubmit={(event) => {
        event.preventDefault();
        void acceptInvitation();
      }}
    >
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          Tenant invitation
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">Create a tenant identity</h1>
        <p className="text-sm text-muted-foreground">
          This account is independent from any identity you use in another tenant.
        </p>
      </div>
      <Input value={email} disabled />
      <Input
        autoComplete="name"
        placeholder="Display name"
        value={displayName}
        onChange={(event) => setDisplayName(event.currentTarget.value)}
      />
      <Input
        autoComplete="new-password"
        minLength={12}
        placeholder="Password for this tenant"
        type="password"
        value={password}
        onChange={(event) => setPassword(event.currentTarget.value)}
      />
      {error ? (
        <div className="rounded-md border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}
      <Button className="w-full" disabled={pending || password.length < 12} type="submit">
        {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
        Accept invitation
      </Button>
    </form>
  );
}
