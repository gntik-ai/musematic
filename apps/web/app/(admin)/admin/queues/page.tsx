import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { HelpContent } from "./help";

export default function QueuesPage() {
  return <GenericAdminSectionPage title="Queues" description="Queue depth and lag." help={<HelpContent />} />;
}
