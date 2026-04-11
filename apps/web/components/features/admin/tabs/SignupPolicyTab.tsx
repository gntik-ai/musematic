"use client";

import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { ApiError } from "@/types/api";
import { signupPolicySchema } from "@/lib/schemas/admin";
import { useSignupPolicy, useSignupPolicyMutation } from "@/lib/hooks/use-admin-settings";
import type { SignupPolicySettings } from "@/lib/types/admin";
import { useToast } from "@/lib/hooks/use-toast";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { SettingsFormActions } from "@/components/features/admin/shared/SettingsFormActions";
import { StaleDataAlert } from "@/components/features/admin/shared/StaleDataAlert";

function toFormValues(data: SignupPolicySettings) {
  return {
    signup_mode: data.signup_mode,
    mfa_enforcement: data.mfa_enforcement,
  };
}

export function SignupPolicyTab() {
  const query = useSignupPolicy();
  const mutation = useSignupPolicyMutation();
  const { toast } = useToast();
  const [isSaved, setIsSaved] = useState(false);
  const [isStale, setIsStale] = useState(false);
  const form = useForm({
    defaultValues: {
      signup_mode: "open" as const,
      mfa_enforcement: "optional" as const,
    },
    resolver: zodResolver(signupPolicySchema),
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
        <CardTitle>Signup policy</CardTitle>
        <p className="text-sm text-muted-foreground">
          Control who can create accounts and whether MFA is enforced at sign-in.
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
                setIsStale(false);
              } catch (error) {
                if (error instanceof ApiError && error.status === 412) {
                  setIsStale(true);
                  return;
                }

                toast({
                  title:
                    error instanceof ApiError
                      ? error.message
                      : "Unable to update signup policy",
                  variant: "destructive",
                });
              }
            })}
          >
            <FormField
              control={form.control}
              name="signup_mode"
              render={({ field }) => (
                <FormItem className="space-y-3">
                  <FormLabel>Signup mode</FormLabel>
                  <FormControl>
                    <fieldset className="grid gap-3">
                      {[
                        {
                          value: "open",
                          label: "Open signups",
                          description: "Any verified user can create an account.",
                        },
                        {
                          value: "invite_only",
                          label: "Invite only",
                          description: "Accounts are created only from invitations.",
                        },
                        {
                          value: "admin_approval",
                          label: "Admin approval",
                          description: "New accounts require manual approval.",
                        },
                      ].map((option) => (
                        <label
                          key={option.value}
                          className="flex cursor-pointer items-start gap-3 rounded-xl border border-border/70 p-4"
                        >
                          <input
                            checked={field.value === option.value}
                            className="mt-1"
                            name={field.name}
                            type="radio"
                            value={option.value}
                            onChange={() => field.onChange(option.value)}
                          />
                          <span>
                            <span className="block font-medium">{option.label}</span>
                            <span className="text-sm text-muted-foreground">
                              {option.description}
                            </span>
                          </span>
                        </label>
                      ))}
                    </fieldset>
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="mfa_enforcement"
              render={({ field }) => (
                <FormItem className="flex items-center justify-between rounded-xl border border-border/70 p-4">
                  <div className="space-y-1">
                    <FormLabel>MFA enforcement</FormLabel>
                    <p className="text-sm text-muted-foreground">
                      Require MFA for all sign-ins across the platform.
                    </p>
                  </div>
                  <FormControl>
                    <Switch
                      aria-label="Toggle MFA enforcement"
                      checked={field.value === "required"}
                      onCheckedChange={(checked) =>
                        field.onChange(checked ? "required" : "optional")
                      }
                    />
                  </FormControl>
                </FormItem>
              )}
            />

            <SettingsFormActions
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
