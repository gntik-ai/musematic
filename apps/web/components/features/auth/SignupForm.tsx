"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
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
import { ApiError } from "@/types/api";
import { useRegisterMutation } from "@/lib/hooks/use-auth-mutations";
import { signupSchema, type SignupFormValues } from "@/lib/schemas/auth-schemas";
import { CaptchaWidget } from "@/components/features/auth/CaptchaWidget";
import { ConsentCheckbox } from "@/components/features/auth/ConsentCheckbox";
import { PasswordStrengthMeter } from "@/components/features/auth/PasswordStrengthMeter";

const CONSENT_VERSION = "2026-04-27";

function getRetryAfter(error: ApiError): number {
  const meta = error.meta as Record<string, unknown> | undefined;
  const direct = meta?.retry_after;
  const details = meta?.details as Record<string, unknown> | undefined;
  const nested = details?.retry_after;
  const value = typeof direct === "number" ? direct : nested;
  return typeof value === "number" && Number.isFinite(value) ? value : 60;
}

export function SignupForm() {
  const router = useRouter();
  const registerMutation = useRegisterMutation();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [retryAfter, setRetryAfter] = useState<number | null>(null);
  const [, setCaptchaToken] = useState<string | null>(null);
  const form = useForm<SignupFormValues>({
    resolver: zodResolver(signupSchema),
    defaultValues: {
      email: "",
      displayName: "",
      password: "",
      aiDisclosureAccepted: false,
      termsAccepted: false,
    },
  });

  const password = form.watch("password");

  useEffect(() => {
    if (retryAfter === null || retryAfter <= 0) {
      return;
    }
    const timer = window.setTimeout(() => {
      setRetryAfter((value) => (value === null ? null : Math.max(value - 1, 0)));
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [retryAfter]);

  const handleSubmit = form.handleSubmit(async (values) => {
    setErrorMessage(null);
    setRetryAfter(null);
    try {
      await registerMutation.mutateAsync({
        email: values.email,
        display_name: values.displayName,
        password: values.password,
      });
      router.push(`/verify-email/pending?email=${encodeURIComponent(values.email)}`);
    } catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        setRetryAfter(getRetryAfter(error));
        return;
      }
      setErrorMessage(
        error instanceof Error ? error.message : "Unable to create your account.",
      );
    }
  });

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          Create account
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">Sign up for Musematic</h1>
        <p className="text-sm text-muted-foreground">
          Use a work email and a strong password to start verification.
        </p>
      </div>
      <Form {...form}>
        <form className="space-y-5" noValidate onSubmit={handleSubmit}>
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Email</FormLabel>
                <FormControl>
                  <Input autoComplete="email" placeholder="name@company.com" type="email" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="displayName"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Display name</FormLabel>
                <FormControl>
                  <Input autoComplete="name" placeholder="Ada Lovelace" {...field} />
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
                  <Input autoComplete="new-password" placeholder="Create a password" type="password" {...field} />
                </FormControl>
                <PasswordStrengthMeter password={password} />
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="aiDisclosureAccepted"
            render={({ field }) => (
              <FormItem>
                <ConsentCheckbox
                  consentVersion={CONSENT_VERSION}
                  type="ai_disclosure"
                  value={field.value}
                  onChange={field.onChange}
                />
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="termsAccepted"
            render={({ field }) => (
              <FormItem>
                <ConsentCheckbox
                  consentVersion={CONSENT_VERSION}
                  type="terms"
                  value={field.value}
                  onChange={field.onChange}
                />
                <FormMessage />
              </FormItem>
            )}
          />
          <CaptchaWidget onTokenChange={setCaptchaToken} />
          {retryAfter !== null && retryAfter > 0 ? (
            <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-700">
              You can try again in {retryAfter} second{retryAfter === 1 ? "" : "s"}.
            </div>
          ) : null}
          {errorMessage ? (
            <div className="rounded-md border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">
              {errorMessage}
            </div>
          ) : null}
          <Button
            aria-busy={registerMutation.isPending}
            className="w-full"
            disabled={registerMutation.isPending || (retryAfter !== null && retryAfter > 0)}
            type="submit"
          >
            {registerMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Creating account
              </>
            ) : (
              "Create account"
            )}
          </Button>
        </form>
      </Form>
    </div>
  );
}
