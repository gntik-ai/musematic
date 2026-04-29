"use client";

import Link from "next/link";
import { zodResolver } from "@hookform/resolvers/zod";
import { ExternalLink, Loader2 } from "lucide-react";
import { useState } from "react";
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
import { listOAuthLinkStatus } from "@/lib/api/auth";
import { useForgotPasswordMutation } from "@/lib/hooks/use-auth-mutations";
import { useOAuthRecoveryMutation } from "@/lib/hooks/use-oauth";
import {
  forgotPasswordSchema,
  type ForgotPasswordFormValues,
} from "@/lib/schemas/auth-schemas";
import type { OAuthLinkResponse, OAuthProviderType } from "@/lib/types/oauth";

const CONFIRMATION_MESSAGE =
  "If an account exists with this email, a reset link has been sent.";

export function ForgotPasswordForm() {
  const [isConfirmed, setIsConfirmed] = useState(false);
  const [submittedEmail, setSubmittedEmail] = useState("");
  const [recoveryLinks, setRecoveryLinks] = useState<OAuthLinkResponse[]>([]);
  const [recoveryError, setRecoveryError] = useState<string | null>(null);
  const forgotPasswordMutation = useForgotPasswordMutation();
  const oauthRecoveryMutation = useOAuthRecoveryMutation();
  const form = useForm<ForgotPasswordFormValues>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: {
      email: "",
    },
  });

  const handleSubmit = form.handleSubmit(async (values) => {
    setSubmittedEmail(values.email);
    setRecoveryLinks([]);
    setRecoveryError(null);
    try {
      await forgotPasswordMutation.mutateAsync(values);
    } catch {
      // Preserve account-enumeration resistance: every server response reaches the same UI.
    } finally {
      setIsConfirmed(true);
      void listOAuthLinkStatus(values.email)
        .then((response) => {
          setRecoveryLinks(response.items);
        })
        .catch(() => {
          setRecoveryLinks([]);
        });
    }
  });

  const startOAuthRecovery = async (providerType: OAuthProviderType) => {
    setRecoveryError(null);
    try {
      const response = await oauthRecoveryMutation.mutateAsync({
        email: submittedEmail,
        providerType,
      });
      window.location.assign(response.redirect_url);
    } catch {
      setRecoveryError("Unable to start linked-provider recovery. Please try again.");
    }
  };

  if (isConfirmed) {
    return (
      <div className="space-y-6">
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
            Check your inbox
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">
            Reset link requested
          </h1>
          <p className="text-sm text-muted-foreground">{CONFIRMATION_MESSAGE}</p>
        </div>
        <Button asChild className="w-full" variant="outline">
          <Link href="/login">Back to login</Link>
        </Button>
        {recoveryLinks.length > 0 ? (
          <div className="space-y-3 rounded-lg border border-border/70 bg-muted/30 p-4">
            <div className="space-y-1">
              <h2 className="text-sm font-semibold">Recover with a linked provider</h2>
              <p className="text-sm text-muted-foreground">
                You can sign in with a connected provider and update your local password later.
              </p>
            </div>
            <div className="grid gap-2">
              {recoveryLinks.map((link) => {
                const isPending =
                  oauthRecoveryMutation.isPending &&
                  oauthRecoveryMutation.variables?.providerType === link.provider_type;

                return (
                  <Button
                    key={link.provider_type}
                    disabled={oauthRecoveryMutation.isPending}
                    type="button"
                    variant="secondary"
                    onClick={() => {
                      void startOAuthRecovery(link.provider_type);
                    }}
                  >
                    {isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <ExternalLink className="h-4 w-4" />
                    )}
                    Sign in with {link.display_name} to recover access
                  </Button>
                );
              })}
            </div>
            {recoveryError ? (
              <p className="text-sm text-destructive">{recoveryError}</p>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          Account recovery
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">
          Forgot your password?
        </h1>
        <p className="text-sm text-muted-foreground">
          Enter your email and we&apos;ll send you a reset link.
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
          <Button
            className="w-full"
            disabled={forgotPasswordMutation.isPending}
            type="submit"
          >
            {forgotPasswordMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Sending reset link
              </>
            ) : (
              "Send reset link"
            )}
          </Button>
          <div className="text-right text-sm">
            <Link
              className={[
                "font-medium text-brand-primary transition hover:text-brand-primary/80",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              ].join(" ")}
              href="/login"
            >
              Back to login
            </Link>
          </div>
        </form>
      </Form>
    </div>
  );
}
