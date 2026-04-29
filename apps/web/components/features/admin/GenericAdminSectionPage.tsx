import type * as React from "react";
import { AdminPage } from "@/components/features/admin/AdminPage";
import { AdminTable, type AdminTableColumn } from "@/components/features/admin/AdminTable";
import { AdminWriteButton } from "@/components/features/admin/AdminWriteButton";
import { EmbeddedGrafanaPanel } from "@/components/features/admin/EmbeddedGrafanaPanel";

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
  actions?: React.ReactNode;
  help?: React.ReactNode;
  children?: React.ReactNode;
}

export function GenericAdminSectionPage({
  title,
  description,
  grafanaPath,
  superAdminOnly = false,
  actions,
  help,
  children,
}: GenericAdminSectionPageProps) {
  return (
    <AdminPage
      title={title}
      description={description}
      actions={
        actions ?? (
          <AdminWriteButton size="sm">
            Create
          </AdminWriteButton>
        )
      }
      help={help ?? <p>{superAdminOnly ? "Super admin scoped." : description ?? title}</p>}
    >
      <div className="space-y-4">
        {children}
        {grafanaPath ? <EmbeddedGrafanaPanel path={grafanaPath} title={title} /> : null}
        <AdminTable columns={columns} rows={rows} savedViewsKey={title.toLowerCase()} />
      </div>
    </AdminPage>
  );
}
