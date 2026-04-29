import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function WarmPoolPage() {
  return <GenericAdminSectionPage title="Warm Pool" description="Runtime warm-pool capacity." help={<HelpContent />} />;
}
