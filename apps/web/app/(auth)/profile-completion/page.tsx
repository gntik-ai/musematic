"use client";

import { useEffect } from "react";
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
import { Select } from "@/components/ui/select";
import { useUpdateProfileMutation } from "@/lib/hooks/use-auth-mutations";
import {
  profileCompletionSchema,
  type ProfileCompletionFormValues,
} from "@/lib/schemas/auth-schemas";
import { useAuthStore } from "@/store/auth-store";

const LOCALES = ["en", "es", "fr", "de", "ja", "zh-CN"] as const;

function defaultLocale(): ProfileCompletionFormValues["locale"] {
  const language = navigator.language.toLowerCase();
  return LOCALES.find((locale) => language.startsWith(locale.toLowerCase())) ?? "en";
}

export default function ProfileCompletionPage() {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);
  const updateMutation = useUpdateProfileMutation();
  const form = useForm<ProfileCompletionFormValues>({
    resolver: zodResolver(profileCompletionSchema),
    defaultValues: {
      displayName: "",
      locale: "en",
      timezone: "UTC",
    },
  });

  useEffect(() => {
    if (user?.status && user.status !== "pending_profile_completion") {
      router.replace("/home");
      return;
    }
    form.reset({
      displayName: user?.displayName || user?.email.split("@", 1)[0] || "",
      locale: defaultLocale(),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    });
  }, [form, router, user]);

  const handleSubmit = form.handleSubmit(async (values) => {
    await updateMutation.mutateAsync({
      display_name: values.displayName,
      locale: values.locale,
      timezone: values.timezone,
    });
    if (user) {
      setUser({
        ...user,
        displayName: values.displayName,
        status: "active",
      });
    }
    router.replace("/home");
  });

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
          Complete profile
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">Finish your account</h1>
        <p className="text-sm text-muted-foreground">
          Confirm your display name, language, and timezone before continuing.
        </p>
      </div>
      <Form {...form}>
        <form className="space-y-5" onSubmit={handleSubmit}>
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
            name="locale"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Language</FormLabel>
                <FormControl>
                  <Select {...field}>
                    {LOCALES.map((locale) => (
                      <option key={locale} value={locale}>
                        {locale}
                      </option>
                    ))}
                  </Select>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="timezone"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Timezone</FormLabel>
                <FormControl>
                  <Input placeholder="Europe/Madrid" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <Button className="w-full" disabled={updateMutation.isPending} type="submit">
            {updateMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Saving profile
              </>
            ) : (
              "Continue"
            )}
          </Button>
        </form>
      </Form>
    </div>
  );
}
