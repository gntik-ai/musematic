"use client";

import { ShieldAlert } from "lucide-react";
import { DriftStatusBadge, LocaleFilePublishForm, LocaleVersionHistory } from "@/components/features/admin-locales";
import { localeOptions } from "@/components/features/preferences/LanguagePicker";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAvailableLocales } from "@/lib/api/locales";
import { useAuthStore } from "@/store/auth-store";

export default function AdminLocalesPage() {
  const roles = useAuthStore((state) => state.user?.roles ?? []);
  const isSuperadmin = roles.includes("superadmin");
  const locales = useAvailableLocales();
  const versions = locales.data ?? [];

  if (!isSuperadmin) {
    return (
      <div className="mx-auto flex min-h-[40vh] max-w-xl items-center justify-center">
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-6">
          <div className="flex items-start gap-3">
            <ShieldAlert className="mt-1 h-5 w-5 text-destructive" />
            <div>
              <h1 className="text-lg font-semibold">Superadmin access required</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Locale file publishing is restricted to superadmins.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold">Locale files</h1>
        <p className="text-sm text-muted-foreground">
          Publish translated catalogue versions and review drift status.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {localeOptions.map((locale) => (
          <Card key={locale.value}>
            <CardContent className="flex items-center justify-between gap-3 p-4">
              <div>
                <p className="font-semibold">{locale.label}</p>
                <p className="text-xs text-muted-foreground">{locale.value}</p>
              </div>
              <DriftStatusBadge status="current" />
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Publish locale file</CardTitle>
        </CardHeader>
        <CardContent>
          <LocaleFilePublishForm />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Version history</CardTitle>
        </CardHeader>
        <CardContent>
          <LocaleVersionHistory versions={versions} />
        </CardContent>
      </Card>
    </div>
  );
}
