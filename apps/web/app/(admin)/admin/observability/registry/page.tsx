import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function ObservabilityRegistryPage() {
  return <GenericAdminSectionPage title="Observability Registry" description="Metrics, logs, and traces inventory." help={<HelpContent />} />;
}
