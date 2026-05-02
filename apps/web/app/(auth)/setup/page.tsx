"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { TenantSetupWizard } from "@/components/features/auth/TenantSetupWizard";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useTenantSetup } from "@/lib/hooks/use-tenant-setup";

function SetupTenantAdminContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const setupQuery = useTenantSetup(token);

  return (
    <div className="space-y-6">
      {!token ? (
        <Alert variant="destructive">
          <AlertTitle>Invite token missing</AlertTitle>
          <AlertDescription>Use the setup link from your invitation.</AlertDescription>
        </Alert>
      ) : null}

      {setupQuery.isLoading ? <Skeleton className="h-96 w-full" /> : null}

      {setupQuery.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Invitation unavailable</AlertTitle>
          <AlertDescription>
            Request a new invitation from your platform administrator.
          </AlertDescription>
          <Button asChild className="mt-4" variant="outline">
            <Link href="/login">Back to login</Link>
          </Button>
        </Alert>
      ) : null}

      {setupQuery.data ? <TenantSetupWizard initial={setupQuery.data} /> : null}
    </div>
  );
}

export default function SetupTenantAdminPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <SetupTenantAdminContent />
    </Suspense>
  );
}
