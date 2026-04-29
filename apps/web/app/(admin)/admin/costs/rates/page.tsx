import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function CostsRatesPage() {
  return <GenericAdminSectionPage title="Cost Rates" description="Provider and infrastructure rate cards." help={<HelpContent />} />;
}
