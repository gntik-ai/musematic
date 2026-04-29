import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function IncidentIntegrationsPage() {
  return <GenericAdminSectionPage title="Incident Integrations" description="PagerDuty, OpsGenie, and incident providers." help={<HelpContent />} />;
}
