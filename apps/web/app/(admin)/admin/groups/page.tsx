import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function GroupsPage() {
  return <GenericAdminSectionPage title="Groups" description="Directory groups and mapped roles." help={<HelpContent />} />;
}
