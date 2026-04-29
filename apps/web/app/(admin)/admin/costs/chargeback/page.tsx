import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function CostsChargebackPage() {
  return <GenericAdminSectionPage title="Chargeback" description="Period cost attribution reports." help={<HelpContent />} />;
}
