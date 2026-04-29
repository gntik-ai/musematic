import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function ModelCatalogPage() {
  return <GenericAdminSectionPage title="Model Catalog" description="Provider models and fallback policies." help={<HelpContent />} />;
}
