"use client";

import { useParams, useRouter } from "next/navigation";
import { EmptyState } from "@/components/shared/EmptyState";
import { IncidentDetail } from "@/components/features/incident-response";
import { useIncident, useResolveIncident, useStartPostMortem } from "@/lib/api/incidents";

export default function OperatorIncidentDetailPage() {
  const router = useRouter();
  const params = useParams<{ incidentId: string }>();
  const incidentId = params.incidentId;
  const incident = useIncident(incidentId);
  const resolveIncident = useResolveIncident();
  const startPostMortem = useStartPostMortem();

  if (incident.isPending) {
    return <EmptyState title="Loading incident" description="Fetching incident detail." />;
  }
  if (!incident.data) {
    return <EmptyState title="Incident unavailable" description="The incident could not be loaded." />;
  }

  return (
    <IncidentDetail
      incident={incident.data}
      isResolving={resolveIncident.isPending}
      onResolve={() =>
        resolveIncident.mutate(incidentId, {
          onSuccess: () => {
            void incident.refetch();
          },
        })
      }
      onStartPostMortem={() =>
        startPostMortem.mutate(incidentId, {
          onSuccess: () => router.push(`/operator/incidents/${incidentId}/post-mortem`),
        })
      }
    />
  );
}
