"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { CommandPalette } from "@/components/layout/command-palette/CommandPalette";
import { CommandPaletteProvider } from "@/components/layout/command-palette/CommandPaletteProvider";
import { MfaEnrollmentDialog } from "@/components/features/auth/mfa-enrollment/MfaEnrollmentDialog";
import { Header } from "@/components/layout/header/Header";
import { Sidebar } from "@/components/layout/sidebar/Sidebar";
import { useAuthStore } from "@/store/auth-store";

export default function MainLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);
  const [mounted, setMounted] = useState(false);

  const redirectTarget = useMemo(() => {
    const query = searchParams.toString();
    return query ? `${pathname}?${query}` : pathname;
  }, [pathname, searchParams]);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (mounted && !isAuthenticated) {
      router.replace(`/login?redirectTo=${encodeURIComponent(redirectTarget)}`);
    }
  }, [isAuthenticated, mounted, redirectTarget, router]);

  if (!mounted || !isAuthenticated) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">Redirecting to login…</div>;
  }

  return (
    <CommandPaletteProvider>
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Header />
          <main className="flex-1 overflow-auto p-6">{children}</main>
          {user && !user.mfaEnrolled ? (
            <MfaEnrollmentDialog
              onEnrolled={() => {
                setUser({ ...user, mfaEnrolled: true });
              }}
              open
            />
          ) : null}
        </div>
        <CommandPalette />
      </div>
    </CommandPaletteProvider>
  );
}
