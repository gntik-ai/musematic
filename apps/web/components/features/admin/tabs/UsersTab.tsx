"use client";

import { useMemo, useState } from "react";
import { formatRelative } from "date-fns";
import { ApiError } from "@/types/api";
import { useAdminUsers, useUserActionMutation } from "@/lib/hooks/use-admin-settings";
import type { AdminUserRow, UserAction, UserStatus } from "@/lib/types/admin";
import { useToast } from "@/lib/hooks/use-toast";
import { useAuthStore } from "@/store/auth-store";
import { DataTable, type DataTableProps } from "@/components/shared/DataTable";
import { SearchInput } from "@/components/shared/SearchInput";
import { StatusBadge, type StatusSemantic } from "@/components/shared/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { UserActionDialog } from "@/components/features/admin/users/UserActionDialog";
import { UserActionsMenu } from "@/components/features/admin/users/UserActionsMenu";
import type { ColumnDef, PaginationState } from "@tanstack/react-table";

const PAGE_SIZE = 20;

function toSemantic(status: UserStatus): StatusSemantic {
  switch (status) {
    case "active":
      return "healthy";
    case "pending_approval":
    case "pending_verification":
      return "warning";
    case "suspended":
      return "inactive";
    case "blocked":
    case "archived":
      return "error";
  }
}

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "Never";
  }

  return formatRelative(new Date(value), new Date());
}

export function UsersTab() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | UserStatus>("all");
  const [page, setPage] = useState(1);
  const [selectedUser, setSelectedUser] = useState<AdminUserRow | null>(null);
  const [pendingAction, setPendingAction] = useState<UserAction | null>(null);
  const currentUserId = useAuthStore((state) => state.user?.id ?? null);
  const { toast } = useToast();

  const usersQuery = useAdminUsers({
    page,
    page_size: PAGE_SIZE,
    search,
    sort: "created_at:desc",
    status: statusFilter,
  });
  const actionMutation = useUserActionMutation(selectedUser?.id ?? "");

  const columns = useMemo<ColumnDef<AdminUserRow>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Name",
        cell: ({ row }) => (
          <div>
            <p className="font-medium">{row.original.name}</p>
            <p className="text-sm text-muted-foreground">{row.original.email}</p>
          </div>
        ),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => (
          <StatusBadge
            label={row.original.status.replace(/_/g, " ")}
            status={toSemantic(row.original.status)}
          />
        ),
      },
      {
        accessorKey: "role",
        header: "Role",
        cell: ({ row }) => (
          <span className="capitalize">{row.original.role.replace(/_/g, " ")}</span>
        ),
      },
      {
        accessorKey: "last_login_at",
        header: "Last login",
        cell: ({ row }) => (
          <span>{formatTimestamp(row.original.last_login_at)}</span>
        ),
      },
      {
        accessorKey: "created_at",
        header: "Created",
        cell: ({ row }) => <span>{formatTimestamp(row.original.created_at)}</span>,
      },
      {
        id: "actions",
        header: "Actions",
        cell: ({ row }) => (
          <div className="flex justify-end">
            <UserActionsMenu
              currentUserId={currentUserId}
              user={row.original}
              onAction={(action) => {
                setSelectedUser(row.original);
                setPendingAction(action);
              }}
            />
          </div>
        ),
      },
    ],
    [currentUserId],
  );

  const onPaginationChange: DataTableProps<AdminUserRow>["onPaginationChange"] = (
    paginationState,
  ) => {
    const nextState =
      typeof paginationState === "function"
        ? paginationState({ pageIndex: page - 1, pageSize: PAGE_SIZE })
        : paginationState;
    const nextPage = (nextState as PaginationState).pageIndex + 1;
    setPage(nextPage);
  };

  return (
    <Card>
      <CardHeader className="space-y-4">
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle>Users</CardTitle>
            <p className="text-sm text-muted-foreground">
              Search, review, and manage platform access for all users.
            </p>
          </div>
          <div className="flex flex-col gap-3 md:w-[28rem] md:flex-row">
            <SearchInput
              defaultValue={search}
              isLoading={usersQuery.isFetching}
              placeholder="Search users by name or email"
              onChange={(value) => {
                setPage(1);
                setSearch(value);
              }}
            />
            <Select
              aria-label="Filter users by status"
              value={statusFilter}
              onChange={(event) => {
                setPage(1);
                setStatusFilter(event.target.value as "all" | UserStatus);
              }}
            >
              <option value="all">All statuses</option>
              <option value="pending_approval">Pending approval</option>
              <option value="active">Active</option>
              <option value="suspended">Suspended</option>
              <option value="blocked">Blocked</option>
            </Select>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <DataTable
          columns={columns}
          data={usersQuery.data?.items ?? []}
          emptyStateMessage="No users matched the current filters."
          enableFiltering={false}
          isLoading={usersQuery.isLoading}
          pageSize={PAGE_SIZE}
          totalCount={usersQuery.data?.total}
          onPaginationChange={onPaginationChange}
        />
      </CardContent>

      <UserActionDialog
        action={pendingAction}
        isPending={actionMutation.isPending}
        open={selectedUser !== null && pendingAction !== null}
        user={selectedUser}
        onConfirm={async () => {
          if (!pendingAction || !selectedUser) {
            return;
          }

          try {
            await actionMutation.mutateAsync(pendingAction);
            toast({
              title: `${selectedUser.name} updated`,
              variant: "success",
            });
            setSelectedUser(null);
            setPendingAction(null);
          } catch (error) {
            toast({
              title:
                error instanceof ApiError ? error.message : "Unable to update user",
              variant: "destructive",
            });
          }
        }}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedUser(null);
            setPendingAction(null);
          }
        }}
      />
    </Card>
  );
}
