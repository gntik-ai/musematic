"use client";

import { useState } from "react";
import { GenericAdminSectionPage } from "@/components/features/admin/GenericAdminSectionPage";
import { AdminWriteButton } from "@/components/features/admin/AdminWriteButton";
import { TwoPersonAuthDialog } from "@/components/features/admin/TwoPersonAuthDialog";
import {
  useCreateTwoPersonAuthRequest,
  useExecuteFailover,
} from "@/lib/hooks/use-admin-mutations";

export default function RegionsPage() {
  const [twoPaOpen, setTwoPaOpen] = useState(false);
  const createTwoPa = useCreateTwoPersonAuthRequest();
  const executeFailover = useExecuteFailover();

  async function requestFailoverApproval() {
    const request = await createTwoPa.mutateAsync({
      action: "multi_region_ops.failover.execute",
      payload: { mode: "test", source_region: "primary", target_region: "secondary" },
    });
    await executeFailover.mutateAsync({
      mode: "test",
      twoPersonAuthToken: request.message ?? request.bulk_action_id ?? "",
    });
    setTwoPaOpen(false);
  }

  return (
    <>
      <GenericAdminSectionPage
        title="Regions"
        description="Replication, failover, and RPO/RTO state."
        superAdminOnly
        actions={
          <AdminWriteButton size="sm" onClick={() => setTwoPaOpen(true)}>
            Initiate failover test
          </AdminWriteButton>
        }
      />
      <TwoPersonAuthDialog
        open={twoPaOpen}
        mode="initiate"
        action="multi_region_ops.failover.execute"
        payload={{ mode: "test", source_region: "primary", target_region: "secondary" }}
        onOpenChange={setTwoPaOpen}
        onConfirm={() => {
          void requestFailoverApproval();
        }}
      />
    </>
  );
}
