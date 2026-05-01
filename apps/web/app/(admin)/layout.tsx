"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { CommandPaletteProvider } from "@/components/layout/command-palette/CommandPaletteProvider";
import { AdminCommandPalette } from "@/components/features/admin/AdminCommandPalette";
import { AdminLayout } from "@/components/features/admin/AdminLayout";
import { useAuthStore } from "@/store/auth-store";

export default function AdminRouteLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const router = useRouter();
  const pathname = usePathname();
  const user = useAuthStore((state) => state.user);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const hasHydrated = useAuthStore((state) => state.hasHydrated);
  const [mounted, setMounted] = useState(false);
  const roles = user?.roles ?? [];
  const isSuperAdmin = roles.includes("superadmin");
  const hasAdminRole = isSuperAdmin || roles.includes("platform_admin");

  const redirectTarget = useMemo(() => {
    if (typeof window === "undefined") {
      return pathname;
    }
    return `${window.location.pathname}${window.location.search}`;
  }, [pathname]);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (mounted && hasHydrated && !isAuthenticated) {
      router.replace(`/login?redirectTo=${encodeURIComponent(redirectTarget)}`);
    }
  }, [hasHydrated, isAuthenticated, mounted, redirectTarget, router]);

  if (!mounted || !hasHydrated || !isAuthenticated) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">Redirecting to login...</div>;
  }

  if (!hasAdminRole) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <div className="max-w-md rounded-md border bg-card p-6 text-center">
          <h1 className="text-xl font-semibold">Admin role required</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Sign in with a platform admin or super admin account.
          </p>
        </div>
      </div>
    );
  }

  return (
    <CommandPaletteProvider>
      <AdminLayout isSuperAdmin={isSuperAdmin}>{children}</AdminLayout>
      <AdminCommandPalette />
    </CommandPaletteProvider>
  );
}
