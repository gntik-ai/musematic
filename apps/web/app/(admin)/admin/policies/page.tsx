import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function PoliciesPage() {
  return <GenericAdminSectionPage title="Policies" description="Platform policy bundles and previews." help={<HelpContent />} />;
}
