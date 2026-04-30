"use client";

import Link from "next/link";
import { useState } from "react";
import { Building2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAdminWorkspaces } from "@/lib/hooks/use-admin-settings";

export function WorkspacesTab() {
  const [search, setSearch] = useState("");
  const workspaces = useAdminWorkspaces(search);
  const t = useTranslations("admin.workspaces");

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Building2 className="h-4 w-4" />
          {t("title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <Input onChange={(event) => setSearch(event.target.value)} placeholder={t("search")} value={search} />
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow><TableHead>{t("name")}</TableHead><TableHead className="w-28">{t("action")}</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {(workspaces.data?.items ?? []).map((workspace) => (
                <TableRow key={workspace.id}>
                  <TableCell>{workspace.name}</TableCell>
                  <TableCell>
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/workspaces/${workspace.id}`}>{t("open")}</Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
