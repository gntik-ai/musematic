"use client";

import { useState } from "react";
import { UserRoundCheck } from "lucide-react";
import { AdminPage } from "@/components/features/admin/AdminPage";
import { AdminTable, type AdminTableColumn } from "@/components/features/admin/AdminTable";
import { AdminWriteButton } from "@/components/features/admin/AdminWriteButton";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { useStartImpersonation } from "@/lib/hooks/use-admin-mutations";
import { useAdminStore } from "@/lib/stores/admin-store";
import { useAuthStore } from "@/store/auth-store";
import { HelpContent } from "./help";

interface AdminUserRow {
  id: string;
  name: string;
  email: string;
  status: string;
  scope: string;
}

const rows: AdminUserRow[] = [
  {
    id: "11111111-1111-4111-8111-111111111111",
    name: "Avery Tenant Admin",
    email: "avery.admin@example.com",
    status: "Active",
    scope: "Tenant",
  },
  {
    id: "22222222-2222-4222-8222-222222222222",
    name: "Riley Workspace User",
    email: "riley.user@example.com",
    status: "Active",
    scope: "Tenant",
  },
];

export default function UsersPage() {
  const roles = useAuthStore((state) => state.user?.roles ?? []);
  const refreshToken = useAuthStore((state) => state.refreshToken);
  const setTokens = useAuthStore((state) => state.setTokens);
  const setActiveImpersonationSession = useAdminStore(
    (state) => state.setActiveImpersonationSession,
  );
  const startImpersonation = useStartImpersonation();
  const [targetUser, setTargetUser] = useState<AdminUserRow | null>(null);
  const [justification, setJustification] = useState("");
  const isSuperAdmin = roles.includes("superadmin");
  const impersonationEnabled = process.env.NEXT_PUBLIC_FEATURE_IMPERSONATION_ENABLED !== "false";

  const columns: AdminTableColumn<AdminUserRow>[] = [
    { key: "name", label: "Name" },
    { key: "email", label: "Email" },
    { key: "status", label: "Status" },
    { key: "scope", label: "Scope" },
    {
      key: "id",
      label: "Actions",
      render: (row) =>
        isSuperAdmin && impersonationEnabled ? (
          <AdminWriteButton
            variant="outline"
            size="sm"
            onClick={() => {
              setTargetUser(row);
              setJustification("");
            }}
          >
            <UserRoundCheck className="h-4 w-4" />
            Impersonate
          </AdminWriteButton>
        ) : (
          <span className="text-sm text-muted-foreground">Scoped</span>
        ),
    },
  ];

  async function submitImpersonation() {
    if (!targetUser || justification.trim().length < 20) {
      return;
    }
    const response = await startImpersonation.mutateAsync({
      target_user_id: targetUser.id,
      justification,
    });
    setTokens({
      accessToken: response.access_token,
      refreshToken: refreshToken ?? "",
      expiresIn: 1800,
    });
    setActiveImpersonationSession({
      sessionId: response.session.session_id,
      impersonatingUsername: "Current super admin",
      effectiveUsername: targetUser.name,
      expiresAt: response.session.expires_at,
    });
    setTargetUser(null);
  }

  return (
    <>
      <AdminPage
        title="Users"
        description="Tenant-scoped user administration."
        actions={<AdminWriteButton size="sm">Create user</AdminWriteButton>}
        help={<HelpContent />}
      >
        <AdminTable columns={columns} rows={rows} savedViewsKey="users" />
      </AdminPage>
      <Dialog open={targetUser !== null} onOpenChange={(open) => !open && setTargetUser(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Impersonate {targetUser?.name}</DialogTitle>
          </DialogHeader>
          <Textarea
            value={justification}
            onChange={(event) => setJustification(event.target.value)}
            placeholder="Enter a specific support or incident justification"
          />
          <DialogFooter>
            <AdminWriteButton
              disabled={justification.trim().length < 20}
              onClick={() => {
                void submitImpersonation();
              }}
            >
              Start impersonation
            </AdminWriteButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
