"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { CommandPalette } from "@/components/layout/command-palette/CommandPalette";
import { CommandPaletteProvider } from "@/components/layout/command-palette/CommandPaletteProvider";
import { RouteCommandRegistration } from "@/components/layout/command-palette/RouteCommandRegistration";
import { MfaEnrollmentDialog } from "@/components/features/auth/mfa-enrollment/MfaEnrollmentDialog";
import { MaintenanceModalProvider } from "@/components/features/platform-status/MaintenanceModalProvider";
import { PlatformStatusBanner } from "@/components/features/platform-status/PlatformStatusBanner";
import { SuspensionBanner } from "@/components/features/shell/SuspensionBanner";
import { Header } from "@/components/layout/header/Header";
import { Sidebar } from "@/components/layout/sidebar/Sidebar";
import { DesktopBestHint } from "@/components/layout/desktop-best-hint/DesktopBestHint";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { useAuthStore } from "@/store/auth-store";

export default function MainLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const router = useRouter();
  const pathname = usePathname();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const hasHydrated = useAuthStore((state) => state.hasHydrated);
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);
  const [mounted, setMounted] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const shouldShowGlobalMfaEnrollment =
    Boolean(user && !user.mfaEnrolled) && pathname !== "/settings/security/mfa";

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
    return <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">Redirecting to login…</div>;
  }

  return (
    <CommandPaletteProvider>
      <div className="flex min-h-screen">
        <RouteCommandRegistration />
        <div className="hidden lg:flex">
          <Sidebar />
        </div>
        <div className="flex min-w-0 flex-1 flex-col">
          <SuspensionBanner />
          <PlatformStatusBanner />
          <Header onOpenMobileNav={() => setMobileNavOpen(true)} />
          <main className="flex-1 overflow-auto p-4 sm:p-6">
            <DesktopBestHint />
            {children}
          </main>
          <MaintenanceModalProvider />
          {shouldShowGlobalMfaEnrollment && user ? (
            <MfaEnrollmentDialog
              onEnrolled={() => {
                setUser({ ...user, mfaEnrolled: true });
              }}
              open
            />
          ) : null}
        </div>
        <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
          <SheetContent className="mr-auto h-full w-full max-w-[280px] rounded-none border-r border-l-0 p-0">
            <Sidebar mobile onNavigate={() => setMobileNavOpen(false)} />
          </SheetContent>
        </Sheet>
        <CommandPalette />
      </div>
    </CommandPaletteProvider>
  );
}
