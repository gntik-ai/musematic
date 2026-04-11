"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CommandPalette } from "@/components/layout/command-palette/CommandPalette";
import { CommandPaletteProvider } from "@/components/layout/command-palette/CommandPaletteProvider";
import { Header } from "@/components/layout/header/Header";
import { Sidebar } from "@/components/layout/sidebar/Sidebar";
import { useAuthStore } from "@/store/auth-store";

export default function MainLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const router = useRouter();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (mounted && !isAuthenticated) {
      router.replace("/login");
    }
  }, [isAuthenticated, mounted, router]);

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
        </div>
        <CommandPalette />
      </div>
    </CommandPaletteProvider>
  );
}
