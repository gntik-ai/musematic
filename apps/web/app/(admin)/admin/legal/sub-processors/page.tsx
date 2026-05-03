"use client";

import { AdminPage } from "@/components/features/admin/AdminPage";
import { AddSubProcessorDialog } from "@/components/features/data-lifecycle/AddSubProcessorDialog";
import { SubProcessorRow } from "@/components/features/data-lifecycle/SubProcessorRow";
import { Skeleton } from "@/components/ui/skeleton";
import { useSubProcessorsAdmin } from "@/lib/hooks/use-data-lifecycle";

export default function AdminSubProcessorsPage() {
  const { data, isLoading } = useSubProcessorsAdmin();

  return (
    <AdminPage
      title="Sub-processors"
      description="Manage the third-party services published on the public sub-processors page."
      actions={<AddSubProcessorDialog />}
    >
      {isLoading ? <Skeleton className="h-64 rounded-md" /> : null}
      {data ? (
        <div className="overflow-hidden rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3">Location</th>
                <th className="px-4 py-3">Data categories</th>
                <th className="px-4 py-3">Active</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.map((item) => (
                <SubProcessorRow key={item.id} item={item} />
              ))}
              {data.length === 0 ? (
                <tr>
                  <td className="px-4 py-6 text-center text-muted-foreground" colSpan={6}>
                    No sub-processors registered.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      ) : null}
    </AdminPage>
  );
}
