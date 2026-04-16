"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { CertificationDetailView } from "@/components/features/trust-workbench/CertificationDetailView";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCertification } from "@/lib/hooks/use-certifications";
import { ApiError } from "@/types/api";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

interface TrustWorkbenchDetailPageProps {
  params: {
    certificationId: string;
  };
}

export default function TrustWorkbenchDetailPage({
  params,
}: TrustWorkbenchDetailPageProps) {
  const workspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const certificationQuery = useCertification(params.certificationId);

  if (certificationQuery.isLoading) {
    return (
      <section className="space-y-6" data-certification-id={params.certificationId}>
        <Skeleton className="h-24 rounded-[2rem]" />
        <Skeleton className="h-16 rounded-2xl" />
        <Skeleton className="h-[720px] rounded-[2rem]" />
      </section>
    );
  }

  if (
    certificationQuery.error instanceof ApiError &&
    certificationQuery.error.status === 404
  ) {
    return (
      <section className="space-y-4">
        <EmptyState
          description="The requested certification record could not be found."
          title="Certification not found"
        />
        <div className="flex justify-center">
          <Button asChild variant="outline">
            <Link href="/trust-workbench">
              <ArrowLeft className="h-4 w-4" />
              Back to queue
            </Link>
          </Button>
        </div>
      </section>
    );
  }

  if (!certificationQuery.data) {
    return (
      <EmptyState
        description="The certification detail view could not be loaded."
        title="Certification unavailable"
      />
    );
  }

  return (
    <CertificationDetailView
      certification={certificationQuery.data}
      workspaceId={workspaceId ?? authWorkspaceId ?? "workspace-unknown"}
    />
  );
}
