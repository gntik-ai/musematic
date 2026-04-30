"use client";

import { useEffect, useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { KeyRound } from "lucide-react";
import { ApiError } from "@/types/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { SettingsFormActions } from "@/components/features/admin/shared/SettingsFormActions";
import { OAuthProviderHistoryTab } from "@/components/features/auth/OAuthProviderHistoryTab";
import { OAuthProviderRateLimitsTab } from "@/components/features/auth/OAuthProviderRateLimitsTab";
import { OAuthProviderReseedDialog } from "@/components/features/auth/OAuthProviderReseedDialog";
import { OAuthProviderRoleMappingsTable } from "@/components/features/auth/OAuthProviderRoleMappingsTable";
import { OAuthProviderRotateSecretDialog } from "@/components/features/auth/OAuthProviderRotateSecretDialog";
import { OAuthProviderSourceBadge } from "@/components/features/auth/OAuthProviderSourceBadge";
import { OAuthProviderStatusPanel } from "@/components/features/auth/OAuthProviderStatusPanel";
import { OAuthProviderTestConnectivityButton } from "@/components/features/auth/OAuthProviderTestConnectivityButton";
import { useToast } from "@/lib/hooks/use-toast";
import { useAdminOAuthProviderMutation, useAdminOAuthProviders } from "@/lib/hooks/use-oauth";
import {
  oauthProviderAdminSchema,
  type OAuthProviderAdminFormValues,
} from "@/lib/schemas/oauth";
import type {
  OAuthProviderAdminResponse,
  OAuthProviderType,
  OAuthProviderUpsertRequest,
} from "@/lib/types/oauth";

const supportedProviders: OAuthProviderType[] = ["google", "github"];

function defaultProvider(providerType: OAuthProviderType): OAuthProviderAdminResponse {
  const scopes =
    providerType === "google"
      ? ["openid", "email", "profile"]
      : ["read:user", "user:email"];

  return {
    id: `${providerType}-placeholder`,
    provider_type: providerType,
    display_name: providerType === "google" ? "Google" : "GitHub",
    enabled: false,
    client_id: "",
    client_secret_ref: "",
    redirect_uri: "https://app.example.com/oauth/callback",
    scopes,
    domain_restrictions: [],
    org_restrictions: [],
    group_role_mapping: {},
    default_role: "viewer",
    require_mfa: false,
    source: "manual",
    last_edited_by: null,
    last_edited_at: null,
    last_successful_auth_at: null,
    created_at: new Date(0).toISOString(),
    updated_at: new Date(0).toISOString(),
  };
}

function mappingToText(mapping: Record<string, string>): string {
  return Object.entries(mapping)
    .map(([group, role]) => `${group}=${role}`)
    .join("\n");
}

function listToText(items: string[]): string {
  return items.join("\n");
}

function toFormValues(
  provider: OAuthProviderAdminResponse,
): OAuthProviderAdminFormValues {
  return {
    client_id: provider.client_id,
    client_secret_ref: provider.client_secret_ref,
    default_role: provider.default_role,
    display_name: provider.display_name,
    domain_restrictions_text: listToText(provider.domain_restrictions),
    enabled: provider.enabled,
    group_role_mapping_text: mappingToText(provider.group_role_mapping),
    org_restrictions_text: listToText(provider.org_restrictions),
    redirect_uri: provider.redirect_uri,
    require_mfa: provider.require_mfa,
    scopes_text: listToText(provider.scopes),
  };
}

function splitLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function mappingFromText(value: string): Record<string, string> {
  return splitLines(value).reduce<Record<string, string>>((accumulator, line) => {
    const [group, role] = line.split("=").map((item) => item.trim());
    if (group && role) {
      accumulator[group] = role;
    }
    return accumulator;
  }, {});
}

function toRequestPayload(
  values: OAuthProviderAdminFormValues,
): OAuthProviderUpsertRequest {
  return {
    client_id: values.client_id.trim(),
    client_secret_ref: values.client_secret_ref.trim(),
    default_role: values.default_role.trim(),
    display_name: values.display_name.trim(),
    domain_restrictions: splitLines(values.domain_restrictions_text),
    enabled: values.enabled,
    group_role_mapping: mappingFromText(values.group_role_mapping_text),
    org_restrictions: splitLines(values.org_restrictions_text),
    redirect_uri: values.redirect_uri.trim(),
    require_mfa: values.require_mfa,
    scopes: splitLines(values.scopes_text),
  };
}

function ProviderConfigCard({
  provider,
}: {
  provider: OAuthProviderAdminResponse;
}) {
  const mutation = useAdminOAuthProviderMutation();
  const { toast } = useToast();
  const t = useTranslations("admin.oauth");
  const [isSaved, setIsSaved] = useState(false);
  const router = useRouter();
  const searchParams = useSearchParams();
  const providerTab = searchParams.get("provider_tab") ?? "configuration";
  const tabs = [
    { id: "configuration", label: t("tabs.configuration") },
    { id: "status", label: t("tabs.status") },
    { id: "role-mappings", label: t("tabs.roleMappings") },
    { id: "history", label: t("tabs.history") },
    { id: "rate-limits", label: t("tabs.rateLimits") },
  ];

  const setProviderTab = (tab: string) => {
    const next = new URLSearchParams(searchParams.toString());
    next.set("provider_tab", tab);
    router.replace(`?${next.toString()}`, { scroll: false });
  };

  const form = useForm<OAuthProviderAdminFormValues>({
    defaultValues: toFormValues(provider),
    resolver: zodResolver(oauthProviderAdminSchema),
  });

  useEffect(() => {
    if (!form.formState.isDirty) {
      form.reset(toFormValues(provider));
    }
  }, [form, provider]);

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 space-y-2">
            <CardTitle className="flex flex-wrap items-center gap-2 text-base">
              <KeyRound className="h-4 w-4 text-brand-accent" />
              {provider.display_name}
              <OAuthProviderSourceBadge source={provider.source} />
            </CardTitle>
            <p className="text-sm text-muted-foreground">
              Configure redirect URI, scopes, restrictions, and default role mapping.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <OAuthProviderTestConnectivityButton providerType={provider.provider_type} />
            <OAuthProviderRotateSecretDialog providerType={provider.provider_type} />
            <OAuthProviderReseedDialog providerType={provider.provider_type} />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <Tabs>
          <TabsList className="flex w-full flex-wrap justify-start gap-1 bg-muted/70">
            {tabs.map((tab) => (
              <TabsTrigger
                className={
                  providerTab === tab.id
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground"
                }
                key={tab.id}
                onClick={() => setProviderTab(tab.id)}
              >
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>
          {providerTab === "configuration" ? (
            <TabsContent>
        <Form {...form}>
          <form
            className="space-y-6"
            onSubmit={form.handleSubmit(async (values) => {
              try {
                await mutation.mutateAsync({
                  payload: toRequestPayload(values),
                  providerType: provider.provider_type,
                });
                setIsSaved(true);
                toast({
                  title: `${provider.display_name} provider saved`,
                  variant: "success",
                });
              } catch (error) {
                toast({
                  title:
                    error instanceof ApiError
                      ? error.message
                      : `Unable to save ${provider.display_name} provider`,
                  variant: "destructive",
                });
              }
            })}
          >
            <div className="grid gap-6 lg:grid-cols-2">
              <FormField
                control={form.control}
                name="display_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Display name</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="default_role"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Default role</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="viewer" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="client_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Client ID</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="oauth-client-id" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="client_secret_ref"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Client secret reference</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="secret://oauth/google" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="redirect_uri"
                render={({ field }) => (
                  <FormItem className="lg:col-span-2">
                    <FormLabel>Redirect URI</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="scopes_text"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Scopes</FormLabel>
                    <FormControl>
                      <Textarea {...field} placeholder="openid\nemail\nprofile" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="group_role_mapping_text"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Group role mapping</FormLabel>
                    <FormControl>
                      <Textarea {...field} placeholder="admins=platform_admin" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="domain_restrictions_text"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Allowed domains</FormLabel>
                    <FormControl>
                      <Textarea {...field} placeholder="example.com" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="org_restrictions_text"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Allowed GitHub organizations</FormLabel>
                    <FormControl>
                      <Textarea {...field} placeholder="musematic" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <FormField
                control={form.control}
                name="enabled"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-xl border border-border/70 p-4">
                    <div>
                      <FormLabel>Enable provider</FormLabel>
                      <p className="text-sm text-muted-foreground">
                        Show this provider on the login screen.
                      </p>
                    </div>
                    <FormControl>
                      <Switch
                        checked={field.value}
                        onCheckedChange={field.onChange}
                      />
                    </FormControl>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="require_mfa"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-xl border border-border/70 p-4">
                    <div>
                      <FormLabel>Require MFA after OAuth</FormLabel>
                      <p className="text-sm text-muted-foreground">
                        Force a second factor for users with MFA enrolled.
                      </p>
                    </div>
                    <FormControl>
                      <Switch
                        checked={field.value}
                        onCheckedChange={field.onChange}
                      />
                    </FormControl>
                  </FormItem>
                )}
              />
            </div>

            <SettingsFormActions
              isDirty={form.formState.isDirty}
              isPending={mutation.isPending}
              isSaved={isSaved}
              onClearSaved={() => setIsSaved(false)}
              onReset={() => form.reset(toFormValues(provider))}
            />
          </form>
        </Form>
            </TabsContent>
          ) : null}
          {providerTab === "status" ? (
            <TabsContent>
              <OAuthProviderStatusPanel provider={provider} />
            </TabsContent>
          ) : null}
          {providerTab === "role-mappings" ? (
            <TabsContent>
              <OAuthProviderRoleMappingsTable provider={provider} />
            </TabsContent>
          ) : null}
          {providerTab === "history" ? (
            <TabsContent>
              <OAuthProviderHistoryTab providerType={provider.provider_type} />
            </TabsContent>
          ) : null}
          {providerTab === "rate-limits" ? (
            <TabsContent>
              <OAuthProviderRateLimitsTab providerType={provider.provider_type} />
            </TabsContent>
          ) : null}
        </Tabs>
      </CardContent>
    </Card>
  );
}

export function OAuthProviderAdminPanel() {
  const providersQuery = useAdminOAuthProviders();

  const providers = useMemo(() => {
    const existing = new Map(
      (providersQuery.data?.providers ?? []).map((provider) => [
        provider.provider_type,
        provider,
      ]),
    );

    return supportedProviders.map(
      (providerType) => existing.get(providerType) ?? defaultProvider(providerType),
    );
  }, [providersQuery.data?.providers]);

  return (
    <div className="space-y-6">
      {providersQuery.isLoading ? (
        <Card>
          <CardContent className="py-8 text-sm text-muted-foreground">
            Loading OAuth provider settings…
          </CardContent>
        </Card>
      ) : null}

      {providers.map((provider) => (
        <ProviderConfigCard key={provider.provider_type} provider={provider} />
      ))}
    </div>
  );
}
