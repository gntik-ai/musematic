"use client";

import { useParams } from "next/navigation";
import { MoreHorizontal, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { WorkspaceOwnerLayout } from "@/components/layout/WorkspaceOwnerLayout";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  useRemoveWorkspaceMember,
  useUpdateWorkspaceMemberRole,
  useWorkspaceMembers,
} from "@/lib/hooks/use-workspace-members";
import type { WorkspaceMember } from "@/lib/schemas/workspace-owner";
import { InviteMemberDialog } from "./_components/InviteMemberDialog";
import { TransferOwnershipDialog } from "./_components/TransferOwnershipDialog";

const roles: WorkspaceMember["role"][] = ["admin", "member", "viewer"];

export default function WorkspaceMembersPage() {
  const params = useParams<{ id: string }>();
  const workspaceId = params.id;
  const members = useWorkspaceMembers(workspaceId);
  const updateRole = useUpdateWorkspaceMemberRole(workspaceId);
  const remove = useRemoveWorkspaceMember(workspaceId);
  const t = useTranslations("workspaces.members");

  return (
    <WorkspaceOwnerLayout title={t("title")} description={t("description")}>
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-end gap-2">
          <TransferOwnershipDialog workspaceId={workspaceId} />
          <InviteMemberDialog workspaceId={workspaceId} />
        </div>
        {members.isLoading ? <Skeleton className="h-72 rounded-lg" /> : null}
        {members.isError ? (
          <EmptyState title={t("unavailable")} description={t("unavailableDescription")} />
        ) : null}
        {members.data ? (
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("user")}</TableHead>
                  <TableHead>{t("role")}</TableHead>
                  <TableHead>{t("joined")}</TableHead>
                  <TableHead className="w-16"><MoreHorizontal className="h-4 w-4" /></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {members.data.items.map((member) => (
                  <TableRow key={member.id}>
                    <TableCell className="font-mono text-xs">{member.user_id}</TableCell>
                    <TableCell>
                      {member.role === "owner" ? (
                        <span className="text-sm font-medium">{t("roles.owner")}</span>
                      ) : (
                        <Select
                          className="w-36"
                          value={member.role}
                          onChange={(event) => {
                            updateRole.mutate({
                              userId: member.user_id,
                              role: event.target.value as WorkspaceMember["role"],
                            });
                          }}
                        >
                          {roles.map((role) => (
                            <option key={role} value={role}>
                              {t(`roles.${role}`)}
                            </option>
                          ))}
                        </Select>
                      )}
                    </TableCell>
                    <TableCell>{new Date(member.created_at).toLocaleDateString()}</TableCell>
                    <TableCell>
                      <Button
                        aria-label={t("remove")}
                        disabled={member.role === "owner"}
                        onClick={() => remove.mutate(member.user_id)}
                        size="icon"
                        variant="ghost"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : null}
      </div>
    </WorkspaceOwnerLayout>
  );
}
