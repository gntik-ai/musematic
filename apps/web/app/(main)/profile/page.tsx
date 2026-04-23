"use client";

import { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { BadgeCheck, ShieldCheck } from "lucide-react";
import { ConnectedAccountsSection } from "@/components/features/auth/ConnectedAccountsSection";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "@/lib/hooks/use-toast";
import { useAuthStore } from "@/store/auth-store";

export default function ProfilePage() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const user = useAuthStore((state) => state.user);
  const message = searchParams.get("message");

  useEffect(() => {
    if (message !== "oauth_linked") {
      return;
    }

    toast({
      title: "OAuth account linked successfully.",
      variant: "success",
    });
    router.replace(pathname);
  }, [message, pathname, router]);

  if (!user) {
    return (
      <Card>
        <CardContent className="py-8 text-sm text-muted-foreground">
          Sign in to review your profile and linked OAuth providers.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.2em] text-brand-accent">
          <BadgeCheck className="h-4 w-4" />
          Identity and access
        </div>
        <div>
          <h1 className="text-3xl font-semibold">Profile</h1>
          <p className="mt-2 max-w-3xl text-muted-foreground">
            Review your account details, roles, and linked single sign-on providers.
          </p>
        </div>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>{user.displayName}</CardTitle>
          <p className="text-sm text-muted-foreground">{user.email}</p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {user.roles.map((role) => (
              <span
                key={role}
                className="rounded-full border border-border/70 bg-muted/40 px-3 py-1 text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground"
              >
                {role.replaceAll("_", " ")}
              </span>
            ))}
          </div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <ShieldCheck className="h-4 w-4 text-brand-accent" />
            MFA {user.mfaEnrolled ? "enabled" : "not enabled"}
          </div>
        </CardContent>
      </Card>

      <ConnectedAccountsSection />
    </div>
  );
}
