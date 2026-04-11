"use client";

import Link from "next/link";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
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
import { useForgotPasswordMutation } from "@/lib/hooks/use-auth-mutations";
import {
  forgotPasswordSchema,
  type ForgotPasswordFormValues,
} from "@/lib/schemas/auth-schemas";

const CONFIRMATION_MESSAGE =
  "If an account exists with this email, a reset link has been sent.";

export function ForgotPasswordForm() {
  const [isConfirmed, setIsConfirmed] = useState(false);
  const forgotPasswordMutation = useForgotPasswordMutation();
  const form = useForm<ForgotPasswordFormValues>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: {
      email: "",
    },
  });

  const handleSubmit = form.handleSubmit(async (values) => {
    try {
      await forgotPasswordMutation.mutateAsync(values);
    } finally {
      setIsConfirmed(true);
    }
  });

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
              className="font-medium text-brand-primary transition hover:text-brand-primary/80"
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
