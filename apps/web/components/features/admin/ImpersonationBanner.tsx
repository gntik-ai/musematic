"use client";

import { LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useEndImpersonation } from "@/lib/hooks/use-admin-mutations";
import { useAdminStore } from "@/lib/stores/admin-store";

export function ImpersonationBanner() {
  const session = useAdminStore((state) => state.activeImpersonationSession);
  const setActiveImpersonationSession = useAdminStore((state) => state.setActiveImpersonationSession);
  const endImpersonation = useEndImpersonation();

  if (!session) {
    return null;
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-warning/15 px-4 py-2 text-sm">
      <span>
        Impersonating {session.effectiveUsername} as {session.impersonatingUsername}
      </span>
      <Button
        variant="outline"
        size="sm"
        onClick={() => {
          endImpersonation.mutate(undefined, {
            onSuccess: () => setActiveImpersonationSession(null),
          });
        }}
      >
        <LogOut className="h-4 w-4" />
        End
      </Button>
    </div>
  );
}
