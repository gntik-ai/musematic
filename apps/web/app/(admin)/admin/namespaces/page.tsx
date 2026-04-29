import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function NamespacesPage() {
  return <GenericAdminSectionPage title="Namespaces" description="Reserved and tenant namespaces." help={<HelpContent />} />;
}
