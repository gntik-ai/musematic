import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function CostsOverviewPage() {
  return <GenericAdminSectionPage title="Cost Overview" description="Platform and tenant spend summary." grafanaPath="d/cost-governance" help={<HelpContent />} />;
}
