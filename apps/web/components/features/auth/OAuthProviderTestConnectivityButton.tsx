"use client";

import { CheckCircle2, Loader2, PlugZap, TriangleAlert, XCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useToast } from "@/lib/hooks/use-toast";
import { useOAuthConnectivityMutation } from "@/lib/hooks/use-oauth";
import type { OAuthProviderType } from "@/lib/types/oauth";

export function OAuthProviderTestConnectivityButton({
  providerType,
}: {
  providerType: OAuthProviderType;
}) {
  const t = useTranslations("admin.oauth");
  const { toast } = useToast();
  const mutation = useOAuthConnectivityMutation(providerType);
  const result = mutation.data;
  const Icon =
    result === undefined
      ? PlugZap
      : result.reachable && result.auth_url_returned
        ? CheckCircle2
        : result.reachable
          ? TriangleAlert
          : XCircle;
  const iconClassName =
    result === undefined
      ? "text-muted-foreground"
      : result.reachable && result.auth_url_returned
        ? "text-emerald-600"
        : result.reachable
          ? "text-amber-600"
          : "text-destructive";

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>
          <Button
            aria-label={t("actions.testConnectivity")}
            disabled={mutation.isPending}
            onClick={async () => {
              try {
                const response = await mutation.mutateAsync();
                toast({
                  title: response.reachable
                    ? t("connectivity.success")
                    : t("connectivity.failure"),
                  description: response.diagnostic,
                  variant: response.reachable ? "success" : "destructive",
                });
              } catch (error) {
                toast({
                  title: t("connectivity.failure"),
                  description: error instanceof Error ? error.message : undefined,
                  variant: "destructive",
                });
              }
            }}
            size="icon"
            variant="outline"
          >
            {mutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Icon className={`h-4 w-4 ${iconClassName}`} />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          {result?.diagnostic ?? t("tooltips.testConnectivity")}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
