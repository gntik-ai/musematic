import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function BackupPage() {
  return <GenericAdminSectionPage title="Backup" description="Backup history and restore controls." superAdminOnly help={<HelpContent />} />;
}
