"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { IncidentTable } from "@/components/features/incident-response";
import { MetricCard } from "@/components/shared/MetricCard";
import { useIncidents } from "@/lib/api/incidents";

export default function OperatorIncidentsPage() {
  const router = useRouter();
  const [status, setStatus] = useState("open");
  const [severity, setSeverity] = useState("");
  const incidents = useIncidents({ status: status || undefined, severity: severity || undefined });
  const allIncidents = useIncidents({});
  const resolved24h = useMemo(() => {
    const cutoff = Date.now() - 24 * 60 * 60 * 1000;
    return (
      allIncidents.data?.filter(
        (incident) =>
          incident.resolved_at && new Date(incident.resolved_at).getTime() >= cutoff,
      ).length ?? 0
    );
  }, [allIncidents.data]);
  const openCount = allIncidents.data?.filter((incident) => incident.status === "open").length ?? 0;

  return (
    <section className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2">
        <MetricCard title="Open" value={openCount} />
        <MetricCard title="Resolved 24h" value={resolved24h} />
      </div>
      <IncidentTable
        incidents={incidents.data ?? []}
        isLoading={incidents.isPending}
        severityFilter={severity}
        statusFilter={status}
        onRowClick={(incident) => router.push(`/operator/incidents/${incident.id}`)}
        onSeverityFilterChange={setSeverity}
        onStatusFilterChange={setStatus}
      />
    </section>
  );
}
