import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function ModelCatalogDetailPage() {
  return <GenericAdminSectionPage title="Model Detail" description="Model cards, usage, and costs." help={<HelpContent />} />;
}
