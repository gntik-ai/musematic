import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";

export default function HealthPage() {
  return <GenericAdminSectionPage title="Health" description="Service health and live platform metrics." grafanaPath="d/platform-overview" />;
}
