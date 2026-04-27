import Link from "next/link";
import { Button } from "@/components/ui/button";

interface OAuthErrorPageProps {
  searchParams?: Promise<{ reason?: string | string[] }>;
}

const MESSAGES: Record<string, string> = {
  domain_not_permitted: "Your email domain is not permitted for this provider.",
  domain_not_allowed: "Your email domain is not permitted for this provider.",
  org_not_permitted: "Your GitHub organization is not permitted.",
  org_not_allowed: "Your GitHub organization is not permitted.",
  expired_state: "The OAuth session expired.",
  oauth_state_expired: "The OAuth session expired.",
  provider_error: "The provider returned an error.",
  network_failure: "The provider could not be reached.",
  user_denied_access: "You denied access to the provider account.",
  access_denied: "You denied access to the provider account.",
};

export default async function OAuthErrorPage({ searchParams }: OAuthErrorPageProps) {
  const resolved = await searchParams;
  const rawReason = Array.isArray(resolved?.reason) ? resolved.reason[0] : resolved?.reason;
  const reason = rawReason ?? "provider_error";

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          OAuth error
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">Unable to finish sign-up</h1>
        <p className="text-sm text-muted-foreground">
          {MESSAGES[reason] ?? "OAuth sign-up could not be completed."}
        </p>
      </div>
      <Button asChild className="w-full">
        <Link href="/signup">Try again</Link>
      </Button>
    </div>
  );
}
