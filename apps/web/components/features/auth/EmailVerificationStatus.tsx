"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { RefreshCw } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { getCurrentAccount } from "@/lib/api/auth";
import { useAuthStore } from "@/store/auth-store";

interface EmailVerificationStatusProps {
  email: string;
}

export function EmailVerificationStatus({ email }: EmailVerificationStatusProps) {
  const router = useRouter();
  const accessToken = useAuthStore((state) => state.accessToken);
  const accountQuery = useQuery({
    queryKey: ["accounts", "me", "verification-status"],
    queryFn: getCurrentAccount,
    enabled: Boolean(accessToken),
    refetchInterval: (query) => {
      if (!query.state.data) {
        return 5000;
      }
      return query.state.data.status === "pending_verification" ? 5000 : false;
    },
  });
  const status = accountQuery.data?.status ?? "pending_verification";

  useEffect(() => {
    if (status === "active") {
      router.push("/login?message=email_verified");
    }
    if (status === "pending_approval") {
      router.push("/waiting-approval");
    }
  }, [router, status]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm text-muted-foreground">Verification email sent to</p>
          <p className="font-medium">{email}</p>
        </div>
        <Badge variant="secondary">{status.replaceAll("_", " ")}</Badge>
      </div>
      <Button
        disabled={!accessToken || accountQuery.isFetching}
        type="button"
        variant="outline"
        onClick={() => {
          void accountQuery.refetch();
        }}
      >
        <RefreshCw className={accountQuery.isFetching ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
        Refresh status
      </Button>
    </div>
  );
}
