import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";

export default function CostsOverviewPage() {
  return <GenericAdminSectionPage title="Cost Overview" description="Platform and tenant spend summary." grafanaPath="d/cost-governance" />;
}
