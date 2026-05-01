import { AdminPage } from "@/components/features/admin/AdminPage";
import { TenantProvisionForm } from "@/components/features/admin/TenantProvisionForm";
import { HelpContent } from "../help";

export default function NewTenantPage() {
  return (
    <AdminPage
      title="Provision tenant"
      description="Create an Enterprise tenant and send the first-admin invitation."
      help={<HelpContent />}
    >
      <TenantProvisionForm />
    </AdminPage>
  );
}
