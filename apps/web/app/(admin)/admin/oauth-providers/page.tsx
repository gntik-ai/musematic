import { TenantScopedOAuthAdminPanel } from "@/components/features/auth/TenantScopedOAuthAdminPanel";
import { HelpContent } from "./help";

export default function OAuthProvidersPage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-normal">OAuth Providers</h1>
        <p className="text-sm text-muted-foreground">Identity provider configuration.</p>
      </div>
      <TenantScopedOAuthAdminPanel />
      <HelpContent />
    </div>
  );
}
