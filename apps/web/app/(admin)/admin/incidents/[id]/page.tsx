import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function IncidentDetailPage() {
  return <GenericAdminSectionPage title="Incident Detail" description="Timeline, runbooks, and post-mortem actions." help={<HelpContent />} />;
}
