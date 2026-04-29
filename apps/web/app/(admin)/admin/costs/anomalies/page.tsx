import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function CostsAnomaliesPage() {
  return <GenericAdminSectionPage title="Cost Anomalies" description="Spend anomaly review queue." help={<HelpContent />} />;
}
