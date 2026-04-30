"use client";

import { useEffect } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { CircleHelp, Save } from "lucide-react";
import { useTranslations } from "next-intl";
import { useForm } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { oauthRateLimitConfigSchema, type OAuthRateLimitConfigValues } from "@/lib/schemas/oauth";
import { useToast } from "@/lib/hooks/use-toast";
import {
  useAdminOAuthProviderRateLimits,
  useOAuthRateLimitMutation,
} from "@/lib/hooks/use-oauth";
import type { OAuthProviderType } from "@/lib/types/oauth";

const fields = [
  "per_ip_max",
  "per_ip_window",
  "per_user_max",
  "per_user_window",
  "global_max",
  "global_window",
] as const;

export function OAuthProviderRateLimitsTab({
  providerType,
}: {
  providerType: OAuthProviderType;
}) {
  const t = useTranslations("admin.oauth");
  const { toast } = useToast();
  const query = useAdminOAuthProviderRateLimits(providerType);
  const mutation = useOAuthRateLimitMutation(providerType);
  const form = useForm<OAuthRateLimitConfigValues>({
    defaultValues: {
      per_ip_max: 10,
      per_ip_window: 60,
      per_user_max: 10,
      per_user_window: 60,
      global_max: 100,
      global_window: 60,
    },
    resolver: zodResolver(oauthRateLimitConfigSchema),
  });

  useEffect(() => {
    if (query.data) {
      form.reset(query.data);
    }
  }, [form, query.data]);

  return (
    <Form {...form}>
      <form
        className="space-y-4"
        onSubmit={form.handleSubmit(async (values) => {
          try {
            await mutation.mutateAsync(values);
            toast({ title: t("rateLimits.saved"), variant: "success" });
          } catch (error) {
            toast({
              title: t("rateLimits.saveFailed"),
              description: error instanceof Error ? error.message : undefined,
              variant: "destructive",
            });
          }
        })}
      >
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {fields.map((fieldName) => (
            <FormField
              control={form.control}
              key={fieldName}
              name={fieldName}
              render={({ field }) => (
                <FormItem>
                  <div className="flex items-center gap-2">
                    <FormLabel>{t(`rateLimits.${fieldName}`)}</FormLabel>
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger>
                          <CircleHelp className="h-4 w-4 text-muted-foreground" />
                        </TooltipTrigger>
                        <TooltipContent>{t(`rateLimits.${fieldName}Help`)}</TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </div>
                  <FormControl>
                    <Input
                      min={1}
                      type="number"
                      {...field}
                      onChange={(event) => field.onChange(Number(event.target.value))}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          ))}
        </div>
        {query.isError ? (
          <p className="text-sm text-destructive">{t("rateLimits.loadFailed")}</p>
        ) : null}
        <Button disabled={mutation.isPending} type="submit">
          <Save className="h-4 w-4" />
          {t("actions.save")}
        </Button>
      </form>
    </Form>
  );
}
