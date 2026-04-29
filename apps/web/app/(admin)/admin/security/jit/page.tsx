import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function JitPage() {
  return <GenericAdminSectionPage title="JIT Credentials" description="Temporary credential grants." help={<HelpContent />} />;
}
