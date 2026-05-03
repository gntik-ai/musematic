import Link from "next/link";
import { AdminPage } from "@/components/features/admin/AdminPage";
import { Card, CardContent } from "@/components/ui/card";

export default function AdminDPAIndexPage() {
  return (
    <AdminPage
      title="Data Processing Agreements"
      description="Per-tenant DPA management. Select a tenant from the tenants admin page to upload or view its DPA."
    >
      <Card>
        <CardContent className="space-y-3 pt-6 text-sm">
          <p>
            DPA management is scoped per-tenant. Open a tenant detail page to
            upload, replace, or download its DPA, or use the navigation below.
          </p>
          <Link
            href="/admin/tenants"
            className="text-sm text-primary underline hover:no-underline"
          >
            Browse tenants →
          </Link>
        </CardContent>
      </Card>
    </AdminPage>
  );
}
