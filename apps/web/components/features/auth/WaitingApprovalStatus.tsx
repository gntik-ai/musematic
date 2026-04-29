"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, Loader2 } from "lucide-react";
import { useWebSocket } from "@/components/providers/WebSocketProvider";
import { getCurrentAccount } from "@/lib/api/auth";
import { useAuthStore } from "@/store/auth-store";
import type { AccountStatus } from "@/types/auth";

interface AccountStatusPayload {
  status?: AccountStatus;
  user_id?: string;
}

function payloadStatus(payload: unknown): AccountStatus | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const status = (payload as AccountStatusPayload).status;
  return typeof status === "string" ? status : null;
}

export function WaitingApprovalStatus() {
  const router = useRouter();
  const wsClient = useWebSocket();
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);
  const [status, setStatus] = useState<AccountStatus | null>(
    user?.status ?? "pending_approval",
  );

  useEffect(() => {
    if (user?.status === "active") {
      router.replace("/home");
    }
  }, [router, user?.status]);

  useEffect(() => {
    let cancelled = false;

    const refreshStatus = async () => {
      try {
        const profile = await getCurrentAccount();
        if (cancelled) {
          return;
        }
        setStatus(profile.status);
        if (user) {
          setUser({
            ...user,
            displayName: profile.display_name,
            status: profile.status,
          });
        }
        if (profile.status === "active") {
          router.replace("/login?message=approval_granted");
        }
      } catch {
        // The page remains useful even if polling is temporarily unavailable.
      }
    };

    void refreshStatus();
    const interval = window.setInterval(() => {
      void refreshStatus();
    }, 15_000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [router, setUser, user]);

  useEffect(() => {
    const channels = user?.id ? [`accounts:${user.id}`, "accounts"] : ["accounts"];
    const unsubscribers = channels.map((channel) =>
      wsClient.subscribe<AccountStatusPayload>(channel, (event) => {
        const nextStatus = payloadStatus(event.payload);
        if (!nextStatus) {
          return;
        }
        setStatus(nextStatus);
        if (nextStatus === "active") {
          router.replace("/login?message=approval_granted");
        }
      }),
    );

    return () => {
      unsubscribers.forEach((unsubscribe) => unsubscribe());
    };
  }, [router, user?.id, wsClient]);

  if (status === "active") {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-700">
        <CheckCircle2 className="h-4 w-4" />
        Approval granted. Redirecting to sign in.
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 rounded-lg border border-border/70 bg-muted/30 p-3 text-sm text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin" />
      Waiting for administrator approval.
    </div>
  );
}
