import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";

export default function ObservabilityDashboardsPage() {
  return <GenericAdminSectionPage title="Dashboards" description="Grafana dashboard registry." grafanaPath="dashboards" />;
}
