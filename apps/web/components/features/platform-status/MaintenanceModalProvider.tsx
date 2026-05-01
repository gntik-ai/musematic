"use client";

import { useEffect, useState } from "react";
import { MaintenanceBlockedActionModal } from "@/components/features/platform-status/MaintenanceBlockedActionModal";
import {
  type MaintenanceBlockedError,
  subscribeMaintenanceBlocked,
} from "@/lib/maintenance-blocked";

export function MaintenanceModalProvider() {
  const [error, setError] = useState<MaintenanceBlockedError | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(
    () =>
      subscribeMaintenanceBlocked((nextError) => {
        setError(nextError);
        setOpen(true);
      }),
    [],
  );

  return (
    <MaintenanceBlockedActionModal
      error={error}
      open={open}
      onOpenChange={setOpen}
    />
  );
}
