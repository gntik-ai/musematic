"use client";

import { useEffect, useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { ApiError } from "@/types/api";
import { emailConfigSchema, testEmailSchema } from "@/lib/schemas/admin";
import {
  useEmailConfig,
  useEmailConfigMutation,
  useSendTestEmailMutation,
} from "@/lib/hooks/use-admin-settings";
import type { EmailDeliveryConfig, TestEmailResult } from "@/lib/types/admin";
import { useToast } from "@/lib/hooks/use-toast";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { SettingsFormActions } from "@/components/features/admin/shared/SettingsFormActions";
import { StaleDataAlert } from "@/components/features/admin/shared/StaleDataAlert";

type EmailFormValues =
  | {
      mode: "smtp";
      host: string;
      port: number;
      username: string;
      new_password?: string;
      encryption: "tls" | "starttls" | "none";
      from_address: string;
      from_name: string;
    }
  | {
      mode: "ses";
      region: string;
      access_key_id: string;
      new_secret_access_key?: string;
      from_address: string;
      from_name: string;
    };

function toEmailFormValues(config: EmailDeliveryConfig): EmailFormValues {
  if (config.mode === "ses" && config.ses) {
    return {
      access_key_id: config.ses.access_key_id,
      from_address: config.from_address,
      from_name: config.from_name,
      mode: "ses",
      region: config.ses.region,
    };
  }

  return {
    encryption: config.smtp?.encryption ?? "starttls",
    from_address: config.from_address,
    from_name: config.from_name,
    host: config.smtp?.host ?? "",
    mode: "smtp",
    port: config.smtp?.port ?? 587,
    username: config.smtp?.username ?? "",
  };
}

export function EmailTab() {
  const query = useEmailConfig();
  const mutation = useEmailConfigMutation();
  const testMutation = useSendTestEmailMutation();
  const { toast } = useToast();
  const [isSaved, setIsSaved] = useState(false);
  const [isStale, setIsStale] = useState(false);
  const [passwordEditMode, setPasswordEditMode] = useState(false);
  const [secretEditMode, setSecretEditMode] = useState(false);
  const [testResult, setTestResult] = useState<TestEmailResult | null>(null);

  const form = useForm<EmailFormValues>({
    defaultValues: {
      encryption: "starttls",
      from_address: "noreply@musematic.dev",
      from_name: "Musematic",
      host: "",
      mode: "smtp",
      port: 587,
      username: "",
    },
    resolver: zodResolver(emailConfigSchema),
  });

  const testEmailForm = useForm({
    defaultValues: {
      recipient: "",
    },
    resolver: zodResolver(testEmailSchema),
  });

  useEffect(() => {
    if (query.data && !form.formState.isDirty) {
      form.reset(toEmailFormValues(query.data));
      setIsStale(false);
      setPasswordEditMode(false);
      setSecretEditMode(false);
    }
  }, [form, query.data, form.formState.isDirty]);

  const mode = form.watch("mode");
  const verificationCopy = useMemo(() => {
    if (!query.data) {
      return "Email delivery state unavailable.";
    }

    if (query.data.verification_status === "verified") {
      return "Delivery is verified and ready for production use.";
    }

    if (query.data.verification_status === "error") {
      return "Verification is failing. New messages may be rejected.";
    }

    return "Verification is pending.";
  }, [query.data]);

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      <Card>
        <CardHeader>
          <CardTitle>Email delivery</CardTitle>
          <p className="text-sm text-muted-foreground">
            Configure SMTP or SES credentials and sender identity for platform emails.
          </p>
        </CardHeader>
        <CardContent className="space-y-6">
          {isStale ? (
            <StaleDataAlert
              onReload={async () => {
                const result = await query.refetch();
                if (result.data) {
                  form.reset(toEmailFormValues(result.data));
                  setIsStale(false);
                }
              }}
            />
          ) : null}

          <Alert>
            <AlertTitle>Delivery status</AlertTitle>
            <AlertDescription>{verificationCopy}</AlertDescription>
          </Alert>

          <Form {...form}>
            <form
              className="space-y-4"
              onSubmit={form.handleSubmit(async (values) => {
                if (!query.data) {
                  return;
                }

                const body: Record<string, unknown> =
                  values.mode === "ses"
                    ? {
                        access_key_id: values.access_key_id,
                        from_address: values.from_address,
                        from_name: values.from_name,
                        mode: "ses",
                        region: values.region,
                        ...(secretEditMode && values.new_secret_access_key
                          ? {
                              new_secret_access_key: values.new_secret_access_key,
                            }
                          : {}),
                      }
                    : {
                        encryption: values.encryption,
                        from_address: values.from_address,
                        from_name: values.from_name,
                        host: values.host,
                        mode: "smtp",
                        port: values.port,
                        username: values.username,
                        ...(passwordEditMode && values.new_password
                          ? { new_password: values.new_password }
                          : {}),
                      };

                try {
                  await mutation.mutateAsync({
                    body,
                    _version: query.data.updated_at,
                  });
                  setIsSaved(true);
                  setPasswordEditMode(false);
                  setSecretEditMode(false);
                } catch (error) {
                  if (error instanceof ApiError && error.status === 412) {
                    setIsStale(true);
                    return;
                  }

                  toast({
                    title:
                      error instanceof ApiError
                        ? error.message
                        : "Unable to update email settings",
                    variant: "destructive",
                  });
                }
              })}
            >
              <FormField
                control={form.control}
                name="mode"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Delivery mode</FormLabel>
                    <FormControl>
                      <Select
                        value={field.value}
                        onChange={(event) => {
                          field.onChange(event.target.value);
                          setPasswordEditMode(false);
                          setSecretEditMode(false);
                        }}
                      >
                        <option value="smtp">SMTP</option>
                        <option value="ses">Amazon SES</option>
                      </Select>
                    </FormControl>
                  </FormItem>
                )}
              />

              {mode === "smtp" ? (
                <>
                  <FormField
                    control={form.control}
                    name="host"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>SMTP host</FormLabel>
                        <FormControl>
                          <Input {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="port"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>SMTP port</FormLabel>
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
                    name="username"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Username</FormLabel>
                        <FormControl>
                          <Input {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="encryption"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Encryption</FormLabel>
                        <FormControl>
                          <Select value={field.value} onChange={field.onChange}>
                            <option value="tls">TLS</option>
                            <option value="starttls">STARTTLS</option>
                            <option value="none">None</option>
                          </Select>
                        </FormControl>
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="new_password"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>SMTP password</FormLabel>
                        <div className="flex gap-3">
                          <FormControl>
                            <Input
                              {...field}
                              aria-label="SMTP password"
                              disabled={!passwordEditMode}
                              type="password"
                              value={
                                passwordEditMode
                                  ? field.value ?? ""
                                  : query.data?.mode === "smtp" &&
                                      query.data.smtp?.password_set
                                    ? "••••••••"
                                    : ""
                              }
                              onChange={(event) => field.onChange(event.target.value)}
                            />
                          </FormControl>
                          <Button
                            aria-label="Update SMTP password"
                            type="button"
                            variant="outline"
                            onClick={() => {
                              setPasswordEditMode(true);
                              field.onChange("");
                            }}
                          >
                            Update Password
                          </Button>
                        </div>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </>
              ) : (
                <>
                  <FormField
                    control={form.control}
                    name="region"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>SES region</FormLabel>
                        <FormControl>
                          <Input {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="access_key_id"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Access key ID</FormLabel>
                        <FormControl>
                          <Input {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="new_secret_access_key"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Secret access key</FormLabel>
                        <div className="flex gap-3">
                          <FormControl>
                            <Input
                              {...field}
                              aria-label="SES secret access key"
                              disabled={!secretEditMode}
                              type="password"
                              value={
                                secretEditMode
                                  ? field.value ?? ""
                                  : query.data?.mode === "ses" &&
                                      query.data.ses?.secret_access_key_set
                                    ? "••••••••"
                                    : ""
                              }
                              onChange={(event) => field.onChange(event.target.value)}
                            />
                          </FormControl>
                          <Button
                            aria-label="Update SES secret access key"
                            type="button"
                            variant="outline"
                            onClick={() => {
                              setSecretEditMode(true);
                              field.onChange("");
                            }}
                          >
                            Update Secret
                          </Button>
                        </div>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </>
              )}

              <FormField
                control={form.control}
                name="from_address"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>From address</FormLabel>
                    <FormControl>
                      <Input type="email" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="from_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>From name</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
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
                    form.reset(toEmailFormValues(query.data));
                    setPasswordEditMode(false);
                    setSecretEditMode(false);
                    setIsStale(false);
                  }
                }}
              />
            </form>
          </Form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Send test email</CardTitle>
          <p className="text-sm text-muted-foreground">
            Validate the active email configuration against a real recipient.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <Form {...testEmailForm}>
            <form
              className="space-y-4"
              onSubmit={testEmailForm.handleSubmit(async (values) => {
                try {
                  const result = await testMutation.mutateAsync(values.recipient);
                  setTestResult(result);
                } catch (error) {
                  setTestResult({
                    success: false,
                    message:
                      error instanceof ApiError
                        ? error.message
                        : "Unable to send test email",
                  });
                }
              })}
            >
              <FormField
                control={testEmailForm.control}
                name="recipient"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Recipient</FormLabel>
                    <FormControl>
                      <Input placeholder="test@example.com" type="email" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <Button disabled={testMutation.isPending} type="submit" variant="outline">
                {testMutation.isPending ? "Sending…" : "Send Test Email"}
              </Button>
            </form>
          </Form>

          {testResult ? (
            <Alert
              className={
                testResult.success
                  ? "border-emerald-500/30 bg-emerald-500/10"
                  : "border-destructive/30 bg-destructive/10"
              }
            >
              <AlertTitle>
                {testResult.success ? "Test email sent" : "Test email failed"}
              </AlertTitle>
              <AlertDescription>{testResult.message}</AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
