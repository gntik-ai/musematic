"use client";

import { useTranslations } from "next-intl";
import { KeyRound, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useRevokeApiKey } from "@/lib/hooks/use-me-api-keys";
import type { UserServiceAccountSummary } from "@/lib/schemas/me";

function formatDate(value: string | null | undefined, emptyLabel: string): string {
  if (!value) {
    return emptyLabel;
  }
  try {
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value));
  } catch {
    return value;
  }
}

function statusLabel(status: string, labels: Record<string, string>): string {
  return labels[status] ?? status;
}

export function ApiKeyTable({ items }: { items: UserServiceAccountSummary[] }) {
  const t = useTranslations("apiKeys.table");
  const revoke = useRevokeApiKey();
  const statusLabels = {
    active: t("status.active"),
    disabled: t("status.disabled"),
    revoked: t("status.revoked"),
  };

  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card px-4 py-10 text-center text-sm text-muted-foreground">
        {t("empty")}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("name")}</TableHead>
            <TableHead>{t("identifier")}</TableHead>
            <TableHead>{t("status.label")}</TableHead>
            <TableHead>{t("created")}</TableHead>
            <TableHead>{t("lastUsed")}</TableHead>
            <TableHead className="w-[96px]">{t("action")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <TableRow key={item.service_account_id}>
              <TableCell>
                <div className="flex items-center gap-2 font-medium">
                  <KeyRound className="h-4 w-4 text-brand-accent" />
                  {item.name}
                </div>
              </TableCell>
              <TableCell className="font-mono text-xs">{item.api_key_prefix}</TableCell>
              <TableCell>
                <Badge variant={item.status === "active" ? "default" : "secondary"}>
                  {statusLabel(item.status, statusLabels)}
                </Badge>
              </TableCell>
              <TableCell>{formatDate(item.created_at, t("never"))}</TableCell>
              <TableCell>{formatDate(item.last_used_at, t("never"))}</TableCell>
              <TableCell>
                <Button
                  aria-label={t("revokeAria", { name: item.name })}
                  disabled={revoke.isPending || item.status !== "active"}
                  size="icon"
                  variant="ghost"
                  onClick={() => revoke.mutate(item.service_account_id)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
