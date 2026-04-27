import { OAuthLinkList } from "@/components/features/auth/OAuthLinkList";

export default function AccountConnectionsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Account connections</h1>
        <p className="text-sm text-muted-foreground">
          Manage Google and GitHub sign-in methods for this account.
        </p>
      </div>
      <OAuthLinkList />
    </div>
  );
}
