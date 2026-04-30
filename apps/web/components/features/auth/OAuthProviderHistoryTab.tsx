"use client";

import { Fragment, useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAdminOAuthProviderHistory } from "@/lib/hooks/use-oauth";
import type { OAuthProviderType } from "@/lib/types/oauth";

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function JsonDiffBlock({
  label,
  value,
}: {
  label: string;
  value: Record<string, unknown> | null;
}) {
  return (
    <div className="min-w-0 rounded-md border border-border bg-muted/30 p-3">
      <p className="text-sm font-medium">{label}</p>
      <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs">
        {JSON.stringify(value ?? {}, null, 2)}
      </pre>
    </div>
  );
}

export function OAuthProviderHistoryTab({
  providerType,
}: {
  providerType: OAuthProviderType;
}) {
  const t = useTranslations("admin.oauth");
  const query = useAdminOAuthProviderHistory(providerType);
  const [expanded, setExpanded] = useState<string | null>(null);
  const entries = useMemo(
    () => query.data?.pages.flatMap((page) => page.entries) ?? [],
    [query.data?.pages],
  );

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-md border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-12" />
              <TableHead>{t("history.timestamp")}</TableHead>
              <TableHead>{t("history.admin")}</TableHead>
              <TableHead>{t("history.action")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {entries.map((entry) => {
              const key = `${entry.timestamp}-${entry.action}`;
              const isExpanded = expanded === key;
              return (
                <Fragment key={key}>
                  <TableRow>
                    <TableCell>
                      <Button
                        aria-label={
                          isExpanded ? t("history.collapse") : t("history.expand")
                        }
                        onClick={() => setExpanded(isExpanded ? null : key)}
                        size="icon"
                        variant="ghost"
                      >
                        {isExpanded ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                      </Button>
                    </TableCell>
                    <TableCell>{formatTimestamp(entry.timestamp)}</TableCell>
                    <TableCell>{entry.admin_id ?? t("history.system")}</TableCell>
                    <TableCell>{entry.action}</TableCell>
                  </TableRow>
                  {isExpanded ? (
                    <TableRow>
                      <TableCell colSpan={4}>
                        <div className="grid gap-3 md:grid-cols-2">
                          <JsonDiffBlock label={t("history.before")} value={entry.before} />
                          <JsonDiffBlock label={t("history.after")} value={entry.after} />
                        </div>
                      </TableCell>
                    </TableRow>
                  ) : null}
                </Fragment>
              );
            })}
            {entries.length === 0 ? (
              <TableRow>
                <TableCell className="text-muted-foreground" colSpan={4}>
                  {query.isLoading ? t("history.loading") : t("history.empty")}
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>
      {query.hasNextPage ? (
        <Button
          disabled={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage()}
          variant="outline"
        >
          {t("history.loadMore")}
        </Button>
      ) : null}
      {query.isError ? <p className="text-sm text-destructive">{t("history.loadFailed")}</p> : null}
    </div>
  );
}
