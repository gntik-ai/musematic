import { AdminPage } from "@/components/features/admin/AdminPage";
import { SuspensionTable } from "@/components/features/admin-security/suspension-table";

/**
 * UPD-050 — Platform-staff suspension queue.
 * Endpoint: `/api/v1/admin/security/suspensions/*` (super-admin only).
 */
export default function AdminSuspensionsPage() {
  return (
    <AdminPage
      title="Account suspensions"
      description="Review auto-suspensions and manual suspensions; lift false positives."
    >
      <SuspensionTable />
    </AdminPage>
  );
}
