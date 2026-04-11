"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useToast } from "@/lib/hooks/use-toast";
import { useAuthStore } from "@/store/auth-store";

export default function AdminLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const router = useRouter();
  const { toast } = useToast();
  const roles = useAuthStore((state) => state.user?.roles ?? []);
  const [mounted, setMounted] = useState(false);
  const hasAccess =
    roles.includes("platform_admin") || roles.includes("superadmin");
  const didNotify = useRef(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted || hasAccess) {
      return;
    }

    if (!didNotify.current) {
      toast({
        title: "You do not have permission to access admin settings",
        variant: "destructive",
      });
      didNotify.current = true;
    }

    router.replace("/home");
  }, [hasAccess, mounted, router, toast]);

  if (!mounted || !hasAccess) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-sm text-muted-foreground">
        Checking access…
      </div>
    );
  }

  return <div className="mx-auto w-full max-w-7xl">{children}</div>;
}
