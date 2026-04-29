import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function ObservabilityDashboardsPage() {
  return <GenericAdminSectionPage title="Dashboards" description="Grafana dashboard registry." grafanaPath="dashboards" help={<HelpContent />} />;
}
