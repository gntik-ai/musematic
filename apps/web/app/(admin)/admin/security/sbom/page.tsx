import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function SbomPage() {
  return <GenericAdminSectionPage title="SBOM" description="Release software bill of materials." help={<HelpContent />} />;
}
