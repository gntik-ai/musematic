"use client";

import { Github, Globe2, Loader2 } from "lucide-react";
import { useToast } from "@/lib/hooks/use-toast";
import { useOAuthAuthorizeMutation, useOAuthProviders } from "@/lib/hooks/use-oauth";
import type { OAuthProviderType } from "@/lib/types/oauth";
import { Button } from "@/components/ui/button";

function providerIcon(providerType: OAuthProviderType) {
  return providerType === "github" ? Github : Globe2;
}

export function OAuthProviderButtons() {
  const providersQuery = useOAuthProviders();
  const authorizeMutation = useOAuthAuthorizeMutation();
  const { toast } = useToast();

  const providers = providersQuery.data?.providers ?? [];

  if (!providersQuery.isLoading && providers.length === 0) {
    return null;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="h-px flex-1 bg-border" />
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-muted-foreground">
          Single sign-on
        </p>
        <div className="h-px flex-1 bg-border" />
      </div>

      <div className="grid gap-3">
        {providers.map((provider) => {
          const Icon = providerIcon(provider.provider_type);
          const isPending =
            authorizeMutation.isPending &&
            authorizeMutation.variables === provider.provider_type;

          return (
            <Button
              key={provider.provider_type}
              aria-label={`Continue with ${provider.display_name}`}
              disabled={authorizeMutation.isPending}
              type="button"
              variant="outline"
              onClick={async () => {
                try {
                  const response = await authorizeMutation.mutateAsync(
                    provider.provider_type,
                  );
                  window.location.assign(response.redirect_url);
                } catch {
                  toast({
                    title: `Unable to start ${provider.display_name} sign-in`,
                    variant: "destructive",
                  });
                }
              }}
            >
              {isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Icon className="h-4 w-4" />
              )}
              Continue with {provider.display_name}
            </Button>
          );
        })}
      </div>
    </div>
  );
}
