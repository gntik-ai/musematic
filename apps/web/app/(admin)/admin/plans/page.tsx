import { AdminPage } from "@/components/features/admin/AdminPage";
import { PlanList } from "@/components/features/admin/PlanList";

export default function AdminPlansPage() {
  return (
    <AdminPage
      title="Plans"
      description="Plan catalogue, public pricing visibility, and published versions."
    >
      <PlanList />
    </AdminPage>
  );
}
