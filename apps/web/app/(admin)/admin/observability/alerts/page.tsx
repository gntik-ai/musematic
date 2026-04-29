import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function ObservabilityAlertsPage() {
  return <GenericAdminSectionPage title="Alerts" description="Prometheus and Loki alert rules." help={<HelpContent />} />;
}
