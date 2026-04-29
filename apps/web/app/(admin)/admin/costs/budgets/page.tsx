import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function CostsBudgetsPage() {
  return <GenericAdminSectionPage title="Budgets" description="Workspace budget thresholds." help={<HelpContent />} />;
}
