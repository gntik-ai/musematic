"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, UserCheck } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { toAuthSession } from "@/lib/api/auth";
import { useSetupTenantAdminMutation } from "@/lib/hooks/use-auth-mutations";
import { toast } from "@/lib/hooks/use-toast";
import { PASSWORD_RULES } from "@/lib/schemas/auth-schemas";
import { useAuthStore } from "@/store/auth-store";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

const setupTenantAdminSchema = z
  .object({
    displayName: z.string().trim().min(2, "Display name is required").max(100),
    password: z
      .string()
      .refine((value) => PASSWORD_RULES.every((rule) => rule.test(value)), {
        message: "Password does not meet policy",
      }),
    confirmPassword: z.string(),
  })
  .refine((value) => value.password === value.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

type SetupTenantAdminFormValues = z.infer<typeof setupTenantAdminSchema>;

function errorMessage(error: unknown): string | null {
  if (!error) {
    return null;
  }
  return error instanceof Error ? error.message : "Setup failed";
}

function SetupTenantAdminContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const setupMutation = useSetupTenantAdminMutation();
  const setAuth = useAuthStore((state) => state.setAuth);
  const form = useForm<SetupTenantAdminFormValues>({
    resolver: zodResolver(setupTenantAdminSchema),
    defaultValues: {
      displayName: "",
      password: "",
      confirmPassword: "",
    },
  });
  const currentPassword = form.watch("password");
  const mutationError = errorMessage(setupMutation.error);

  const submit = form.handleSubmit(async (values) => {
    const response = await setupMutation.mutateAsync({
      token,
      display_name: values.displayName,
      password: values.password,
    });
    setAuth(toAuthSession(response));
    toast({ title: "Account ready", variant: "success" });
    router.replace("/home");
  });

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          Tenant setup
        </p>
        <h1 className="text-3xl font-semibold tracking-normal">Create your admin account</h1>
      </div>

      {!token ? (
        <Alert variant="destructive">
          <AlertTitle>Invite token missing</AlertTitle>
          <AlertDescription>Use the setup link from your invitation.</AlertDescription>
        </Alert>
      ) : null}

      {mutationError ? (
        <Alert variant="destructive">
          <AlertTitle>Setup failed</AlertTitle>
          <AlertDescription>{mutationError}</AlertDescription>
        </Alert>
      ) : null}

      <Form {...form}>
        <form className="space-y-5" onSubmit={submit}>
          <FormField
            control={form.control}
            name="displayName"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Display name</FormLabel>
                <FormControl>
                  <Input autoComplete="name" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Password</FormLabel>
                <FormControl>
                  <Input autoComplete="new-password" type="password" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <div className="grid gap-2 rounded-md border bg-background p-3 text-sm">
            {PASSWORD_RULES.map((rule) => (
              <div
                key={rule.key}
                className={rule.test(currentPassword) ? "text-emerald-600" : "text-muted-foreground"}
              >
                {rule.label}
              </div>
            ))}
          </div>
          <FormField
            control={form.control}
            name="confirmPassword"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Confirm password</FormLabel>
                <FormControl>
                  <Input autoComplete="new-password" type="password" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <Button
            className="w-full"
            disabled={!token || setupMutation.isPending}
            type="submit"
          >
            {setupMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <UserCheck className="h-4 w-4" />
            )}
            Complete setup
          </Button>
        </form>
      </Form>
    </div>
  );
}

export default function SetupTenantAdminPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <SetupTenantAdminContent />
    </Suspense>
  );
}
