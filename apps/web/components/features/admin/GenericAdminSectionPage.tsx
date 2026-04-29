import { AdminPage } from "@/components/features/admin/AdminPage";
import { AdminTable, type AdminTableColumn } from "@/components/features/admin/AdminTable";
import { EmbeddedGrafanaPanel } from "@/components/features/admin/EmbeddedGrafanaPanel";
import { Button } from "@/components/ui/button";

interface GenericAdminRow {
  id: string;
  name: string;
  status: string;
  scope: string;
}

const columns: AdminTableColumn<GenericAdminRow>[] = [
  { key: "name", label: "Name" },
  { key: "status", label: "Status" },
  { key: "scope", label: "Scope" },
];

const rows: GenericAdminRow[] = [
  { id: "primary", name: "Primary", status: "Ready", scope: "Tenant" },
  { id: "secondary", name: "Secondary", status: "Pending", scope: "Platform" },
];

interface GenericAdminSectionPageProps {
  title: string;
  description?: string;
  grafanaPath?: string;
  superAdminOnly?: boolean;
}

export function GenericAdminSectionPage({
  title,
  description,
  grafanaPath,
  superAdminOnly = false,
}: GenericAdminSectionPageProps) {
  return (
    <AdminPage
      title={title}
      description={description}
      actions={
        <Button size="sm">
          Create
        </Button>
      }
      help={<p>{superAdminOnly ? "Super admin scoped." : description ?? title}</p>}
    >
      <div className="space-y-4">
        {grafanaPath ? <EmbeddedGrafanaPanel path={grafanaPath} title={title} /> : null}
        <AdminTable columns={columns} rows={rows} />
      </div>
    </AdminPage>
  );
}
