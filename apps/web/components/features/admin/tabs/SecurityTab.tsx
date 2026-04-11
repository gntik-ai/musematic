"use client";

import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { ApiError } from "@/types/api";
import { securityPolicySchema } from "@/lib/schemas/admin";
import {
  useSecurityPolicy,
  useSecurityPolicyMutation,
} from "@/lib/hooks/use-admin-settings";
import type { SecurityPolicySettings } from "@/lib/types/admin";
import { useToast } from "@/lib/hooks/use-toast";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { SettingsFormActions } from "@/components/features/admin/shared/SettingsFormActions";
import { StaleDataAlert } from "@/components/features/admin/shared/StaleDataAlert";

function toFormValues(data: SecurityPolicySettings) {
  return {
    lockout_duration_minutes: data.lockout_duration_minutes,
    lockout_max_attempts: data.lockout_max_attempts,
    password_expiry_days: data.password_expiry_days,
    password_min_length: data.password_min_length,
    password_require_digit: data.password_require_digit,
    password_require_lowercase: data.password_require_lowercase,
    password_require_special: data.password_require_special,
    password_require_uppercase: data.password_require_uppercase,
    session_duration_minutes: data.session_duration_minutes,
  };
}

export function SecurityTab() {
  const query = useSecurityPolicy();
  const mutation = useSecurityPolicyMutation();
  const { toast } = useToast();
  const [isSaved, setIsSaved] = useState(false);
  const [isStale, setIsStale] = useState(false);

  const form = useForm({
    defaultValues: {
      lockout_duration_minutes: 15,
      lockout_max_attempts: 5,
      password_expiry_days: null as number | null,
      password_min_length: 12,
      password_require_digit: true,
      password_require_lowercase: true,
      password_require_special: true,
      password_require_uppercase: true,
      session_duration_minutes: 480,
    },
    mode: "onChange",
    resolver: zodResolver(securityPolicySchema),
  });

  useEffect(() => {
    if (query.data && !form.formState.isDirty) {
      form.reset(toFormValues(query.data));
      setIsStale(false);
    }
  }, [form, query.data, form.formState.isDirty]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Security policy</CardTitle>
        <p className="text-sm text-muted-foreground">
          Password requirements, session lifetime, and account lockout controls.
        </p>
      </CardHeader>
      <CardContent className="space-y-6">
        {isStale ? (
          <StaleDataAlert
            onReload={async () => {
              const result = await query.refetch();
              if (result.data) {
                form.reset(toFormValues(result.data));
                setIsStale(false);
              }
            }}
          />
        ) : null}
        <Form {...form}>
          <form
            className="space-y-6"
            onSubmit={form.handleSubmit(async (values) => {
              if (!query.data) {
                return;
              }

              try {
                await mutation.mutateAsync({
                  body: values,
                  _version: query.data.updated_at,
                });
                setIsSaved(true);
              } catch (error) {
                if (error instanceof ApiError && error.status === 412) {
                  setIsStale(true);
                  return;
                }

                toast({
                  title:
                    error instanceof ApiError
                      ? error.message
                      : "Unable to update security settings",
                  variant: "destructive",
                });
              }
            })}
          >
            <div className="grid gap-6 lg:grid-cols-3">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Password policy</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <FormField
                    control={form.control}
                    name="password_min_length"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Minimum password length</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            {...field}
                            value={field.value}
                            onChange={(event) => field.onChange(event.target.value)}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  {[
                    {
                      name: "password_require_uppercase" as const,
                      label: "Require uppercase letters",
                    },
                    {
                      name: "password_require_lowercase" as const,
                      label: "Require lowercase letters",
                    },
                    {
                      name: "password_require_digit" as const,
                      label: "Require digits",
                    },
                    {
                      name: "password_require_special" as const,
                      label: "Require special characters",
                    },
                  ].map((option) => (
                    <FormField
                      key={option.name}
                      control={form.control}
                      name={option.name}
                      render={({ field }) => (
                        <FormItem className="flex items-center justify-between rounded-xl border border-border/70 p-3">
                          <FormLabel>{option.label}</FormLabel>
                          <FormControl>
                            <Switch
                              checked={field.value}
                              onCheckedChange={field.onChange}
                            />
                          </FormControl>
                        </FormItem>
                      )}
                    />
                  ))}
                  <FormField
                    control={form.control}
                    name="password_expiry_days"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Password expiry (days)</FormLabel>
                        <FormControl>
                          <Input
                            placeholder="No expiry"
                            type="number"
                            {...field}
                            value={field.value ?? ""}
                            onChange={(event) => field.onChange(event.target.value)}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Session</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <FormField
                    control={form.control}
                    name="session_duration_minutes"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Session duration (minutes)</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            {...field}
                            value={field.value}
                            onChange={(event) => field.onChange(event.target.value)}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Lockout</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <FormField
                    control={form.control}
                    name="lockout_max_attempts"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Maximum failed attempts</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            {...field}
                            value={field.value}
                            onChange={(event) => field.onChange(event.target.value)}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="lockout_duration_minutes"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Lockout duration (minutes)</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            {...field}
                            value={field.value}
                            onChange={(event) => field.onChange(event.target.value)}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>
            </div>

            <Alert>
              <AlertTitle>Authentication rollout note</AlertTitle>
              <AlertDescription>
                Changes apply only to new authentication events — existing active
                sessions are not affected.
              </AlertDescription>
            </Alert>

            <SettingsFormActions
              disableSave={!form.formState.isValid}
              isDirty={form.formState.isDirty}
              isPending={mutation.isPending}
              isSaved={isSaved}
              onClearSaved={() => setIsSaved(false)}
              onReset={() => {
                if (query.data) {
                  form.reset(toFormValues(query.data));
                  setIsStale(false);
                }
              }}
            />
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
