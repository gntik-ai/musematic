"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useIBORSyncHistory } from "@/lib/hooks/use-ibor-admin";

export function SyncHistoryDrillDown({ connectorId }: { connectorId: string | null }) {
  const [cursor, setCursor] = useState<string | null>(null);
  const history = useIBORSyncHistory(connectorId, cursor);
  const t = useTranslations("admin.ibor.history");

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">{t("title")}</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <Table>
          <TableHeader>
            <TableRow><TableHead>{t("status")}</TableHead><TableHead>{t("started")}</TableHead><TableHead>{t("counts")}</TableHead></TableRow>
          </TableHeader>
          <TableBody>
            {(history.data?.items ?? []).map((run) => (
              <TableRow key={run.id}>
                <TableCell>{run.status}</TableCell>
                <TableCell>{new Date(run.started_at).toLocaleString()}</TableCell>
                <TableCell className="font-mono text-xs">{JSON.stringify(run.counts)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <Button disabled={!history.data?.next_cursor} onClick={() => setCursor(history.data?.next_cursor ?? null)} size="sm" variant="outline">
          {t("nextPage")}
        </Button>
      </CardContent>
    </Card>
  );
}
