"use client";

import { useMemo, useState } from "react";
import { ExternalLink, Link2, Loader2, Unplug } from "lucide-react";
import { ApiError } from "@/types/api";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/lib/hooks/use-toast";
import {
  useOAuthLinkMutation,
  useOAuthLinks,
  useOAuthProviders,
  useOAuthUnlinkMutation,
} from "@/lib/hooks/use-oauth";
import type { OAuthLinkResponse, OAuthProviderType } from "@/lib/types/oauth";

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "Never";
  }

  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function LinkedAccountCard({
  link,
  onUnlink,
  pendingProvider,
}: {
  link: OAuthLinkResponse;
  onUnlink: (providerType: OAuthProviderType) => void;
  pendingProvider: OAuthProviderType | null;
}) {
  const isPending = pendingProvider === link.provider_type;

  return (
    <div className="rounded-2xl border border-border/70 bg-muted/30 p-4">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Link2 className="h-4 w-4 text-brand-accent" />
            <p className="font-medium">{link.display_name}</p>
          </div>
          <div className="space-y-1 text-sm text-muted-foreground">
            <p>{link.external_email ?? "No external email available"}</p>
            <p>Connected {formatTimestamp(link.linked_at)}</p>
            <p>Last sign-in {formatTimestamp(link.last_login_at)}</p>
          </div>
        </div>
        <Button
          disabled={pendingProvider !== null}
          type="button"
          variant="outline"
          onClick={() => onUnlink(link.provider_type)}
        >
          {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Unplug className="h-4 w-4" />}
          Unlink
        </Button>
      </div>
    </div>
  );
}

export function ConnectedAccountsSection() {
  const linksQuery = useOAuthLinks();
  const providersQuery = useOAuthProviders();
  const linkMutation = useOAuthLinkMutation();
  const unlinkMutation = useOAuthUnlinkMutation();
  const { toast } = useToast();
  const [pendingProvider, setPendingProvider] = useState<OAuthProviderType | null>(null);
  const [confirmProvider, setConfirmProvider] = useState<OAuthProviderType | null>(null);
  const [inlineError, setInlineError] = useState<string | null>(null);

  const links = linksQuery.data?.items ?? [];
  const availableProviders = useMemo(() => {
    const linked = new Set(links.map((item) => item.provider_type));
    return (providersQuery.data?.providers ?? []).filter(
      (provider) => !linked.has(provider.provider_type),
    );
  }, [links, providersQuery.data?.providers]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Connected accounts</CardTitle>
        <p className="text-sm text-muted-foreground">
          Link Google or GitHub to sign in without using a local password.
        </p>
      </CardHeader>
      <CardContent className="space-y-6">
        {inlineError ? (
          <Alert className="border-destructive/30 bg-destructive/10">
            <AlertTitle>Unable to update linked accounts</AlertTitle>
            <AlertDescription>{inlineError}</AlertDescription>
          </Alert>
        ) : null}

        <div className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-[0.2em] text-muted-foreground">
            Linked providers
          </h2>
          {linksQuery.isLoading ? (
            <p className="text-sm text-muted-foreground">Loading linked accounts…</p>
          ) : links.length > 0 ? (
            <div className="space-y-3">
              {links.map((link) => (
                <LinkedAccountCard
                  key={link.provider_type}
                  link={link}
                  pendingProvider={pendingProvider}
                  onUnlink={(providerType) => {
                    setInlineError(null);
                    setConfirmProvider(providerType);
                  }}
                />
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No external providers are linked to this account yet.
            </p>
          )}
        </div>

        <div className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-[0.2em] text-muted-foreground">
            Available providers
          </h2>
          {providersQuery.isLoading ? (
            <p className="text-sm text-muted-foreground">Loading providers…</p>
          ) : availableProviders.length > 0 ? (
            <div className="grid gap-3 md:grid-cols-2">
              {availableProviders.map((provider) => {
                const isPending = pendingProvider === provider.provider_type;

                return (
                  <Button
                    key={provider.provider_type}
                    disabled={pendingProvider !== null}
                    type="button"
                    variant="outline"
                    onClick={async () => {
                      setInlineError(null);
                      setPendingProvider(provider.provider_type);
                      try {
                        const response = await linkMutation.mutateAsync(
                          provider.provider_type,
                        );
                        window.location.assign(response.redirect_url);
                      } catch {
                        toast({
                          title: `Unable to start ${provider.display_name} linking`,
                          variant: "destructive",
                        });
                        setPendingProvider(null);
                      }
                    }}
                  >
                    {isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <ExternalLink className="h-4 w-4" />
                    )}
                    Link {provider.display_name}
                  </Button>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              All enabled providers are already linked.
            </p>
          )}
        </div>

        <ConfirmDialog
          cancelLabel="Keep linked"
          confirmLabel="Unlink provider"
          description="You can unlink this provider as long as another sign-in method remains available."
          isLoading={unlinkMutation.isPending}
          open={confirmProvider !== null}
          title="Unlink OAuth provider"
          variant="destructive"
          onConfirm={async () => {
            if (!confirmProvider) {
              return;
            }
            setPendingProvider(confirmProvider);
            try {
              await unlinkMutation.mutateAsync(confirmProvider);
              setConfirmProvider(null);
              setPendingProvider(null);
            } catch (error) {
              setConfirmProvider(null);
              setPendingProvider(null);
              if (error instanceof ApiError && error.status === 409) {
                setInlineError(
                  "Cannot unlink: this is your only authentication method.",
                );
                return;
              }
              setInlineError(
                error instanceof Error
                  ? error.message
                  : "Unable to unlink the selected provider.",
              );
            }
          }}
          onOpenChange={(open) => {
            if (!open) {
              setConfirmProvider(null);
            }
          }}
        />
      </CardContent>
    </Card>
  );
}
