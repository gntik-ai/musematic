"use client";

import Link from "next/link";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
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
import { getLockoutSeconds, isMfaChallengeResponse, type LoginSuccessResponse } from "@/lib/api/auth";
import { useLoginMutation } from "@/lib/hooks/use-auth-mutations";
import { loginSchema, type LoginFormValues } from "@/lib/schemas/auth-schemas";
import { ApiError } from "@/types/api";

interface LoginFormProps {
  onLockout: (lockoutSeconds: number) => void;
  onMfaChallenge: (sessionToken: string) => void;
  onSuccess: (response: LoginSuccessResponse) => void;
}

const NETWORK_ERROR_MESSAGE =
  "Unable to connect to the server. Please check your connection and try again.";

export function LoginForm({
  onLockout,
  onMfaChallenge,
  onSuccess,
}: LoginFormProps) {
  const [isHydrated, setIsHydrated] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const loginMutation = useLoginMutation();
  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: "",
      password: "",
    },
  });

  useEffect(() => {
    setIsHydrated(true);
  }, []);

  const handleSubmit = form.handleSubmit(async (values) => {
    setErrorMessage(null);

    try {
      const response = await loginMutation.mutateAsync(values);

      if (isMfaChallengeResponse(response)) {
        onMfaChallenge(response.session_token);
        return;
      }

      onSuccess(response);
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.code === "INVALID_CREDENTIALS") {
          setErrorMessage("Invalid email or password");
          return;
        }

        if (error.code === "ACCOUNT_LOCKED") {
          const lockoutSeconds = getLockoutSeconds(error);
          if (lockoutSeconds !== null) {
            onLockout(lockoutSeconds);
            return;
          }
        }
      }

      setErrorMessage(NETWORK_ERROR_MESSAGE);
    }
  });

  return (
    <div className="space-y-6" data-auth-ready={isHydrated ? "true" : "false"}>
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          Secure access
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">Sign in to Musematic</h1>
        <p className="text-sm text-muted-foreground">
          Use your workspace credentials to continue into the control surface.
        </p>
      </div>
      <Form {...form}>
        <form className="space-y-5" onSubmit={handleSubmit}>
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Email</FormLabel>
                <FormControl>
                  <Input
                    autoComplete="email"
                    placeholder="name@company.com"
                    type="email"
                    {...field}
                  />
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
                  <Input
                    autoComplete="current-password"
                    placeholder="Enter your password"
                    type="password"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          {errorMessage ? (
            <div
              className="rounded-xl border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive"
              role="alert"
            >
              {errorMessage}
            </div>
          ) : null}
          <Button
            aria-busy={loginMutation.isPending}
            className="w-full"
            disabled={loginMutation.isPending || !isHydrated}
            type="submit"
          >
            {loginMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Signing in
              </>
            ) : (
              "Sign in"
            )}
          </Button>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Need help getting back in?</span>
            <Link
              className={[
                "font-medium text-brand-primary transition hover:text-brand-primary/80",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              ].join(" ")}
              href="/forgot-password"
            >
              Forgot password?
            </Link>
          </div>
        </form>
      </Form>
    </div>
  );
}
