"use client";

import Link from "next/link";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useResetPasswordMutation } from "@/lib/hooks/use-auth-mutations";
import {
  evaluatePasswordRules,
  resetPasswordSchema,
  type ResetPasswordFormValues,
} from "@/lib/schemas/auth-schemas";
import { ApiError } from "@/types/api";

interface ResetPasswordFormProps {
  token: string;
}

export function ResetPasswordForm({ token }: ResetPasswordFormProps) {
  const router = useRouter();
  const [tokenError, setTokenError] = useState<string | null>(null);
  const resetPasswordMutation = useResetPasswordMutation();
  const form = useForm<ResetPasswordFormValues>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: {
      newPassword: "",
      confirmPassword: "",
    },
    mode: "onChange",
  });

  const newPassword = form.watch("newPassword");
  const rules = useMemo(
    () => evaluatePasswordRules(newPassword ?? ""),
    [newPassword],
  );

  const canSubmit =
    rules.every((rule) => rule.satisfied) &&
    form.watch("confirmPassword") === newPassword &&
    !resetPasswordMutation.isPending;

  const handleSubmit = form.handleSubmit(async (values) => {
    setTokenError(null);

    try {
      await resetPasswordMutation.mutateAsync({
        token,
        new_password: values.newPassword,
      });
      router.push("/login?message=password_updated");
    } catch (error) {
      if (
        error instanceof ApiError &&
        (error.code === "TOKEN_EXPIRED" || error.code === "TOKEN_ALREADY_USED")
      ) {
        setTokenError("This reset link is no longer valid.");
        return;
      }

      setTokenError("Unable to update your password right now.");
    }
  });

  if (tokenError) {
    return (
      <div className="space-y-6">
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
            Reset link issue
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">This link can&apos;t be used</h1>
          <p className="text-sm text-muted-foreground">{tokenError}</p>
        </div>
        <Button asChild className="w-full">
          <Link href="/forgot-password">Request a new link</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          Reset password
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">Set new password</h1>
        <p className="text-sm text-muted-foreground">
          Choose a strong password that meets every requirement below.
        </p>
      </div>
      <Form {...form}>
        <form className="space-y-5" onSubmit={handleSubmit}>
          <FormField
            control={form.control}
            name="newPassword"
            render={({ field }) => (
              <FormItem>
                <FormLabel>New password</FormLabel>
                <FormControl>
                  <Input
                    autoComplete="new-password"
                    placeholder="Choose a strong password"
                    type="password"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <ul className="space-y-2 rounded-2xl border border-border/70 bg-muted/35 p-4 text-sm">
            {rules.map((rule) => (
              <li
                key={rule.key}
                className="flex items-center gap-2"
                data-state={rule.satisfied ? "passed" : "pending"}
              >
                <span
                  aria-hidden="true"
                  className={rule.satisfied ? "text-emerald-500" : "text-muted-foreground"}
                >
                  {rule.satisfied ? "✓" : "✗"}
                </span>
                <span>{rule.label}</span>
              </li>
            ))}
          </ul>
          <FormField
            control={form.control}
            name="confirmPassword"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Confirm password</FormLabel>
                <FormControl>
                  <Input
                    autoComplete="new-password"
                    placeholder="Confirm your password"
                    type="password"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <Button className="w-full" disabled={!canSubmit} type="submit">
            {resetPasswordMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Updating password
              </>
            ) : (
              "Update password"
            )}
          </Button>
        </form>
      </Form>
    </div>
  );
}
