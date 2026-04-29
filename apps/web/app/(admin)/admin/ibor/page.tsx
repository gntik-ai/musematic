import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function IborPage() {
  return <GenericAdminSectionPage title="IBOR Connectors" description="Identity broker sync status." help={<HelpContent />} />;
}
