"use client";

import Link from "next/link";
import { useState } from "react";
import { Building2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAdminWorkspaces } from "@/lib/hooks/use-admin-settings";

export function WorkspacesTab() {
  const [search, setSearch] = useState("");
  const workspaces = useAdminWorkspaces(search);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Building2 className="h-4 w-4" />
          Workspaces
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <Input onChange={(event) => setSearch(event.target.value)} placeholder="Search workspaces" value={search} />
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow><TableHead>Name</TableHead><TableHead className="w-28">Action</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {(workspaces.data?.items ?? []).map((workspace) => (
                <TableRow key={workspace.id}>
                  <TableCell>{workspace.name}</TableCell>
                  <TableCell>
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/workspaces/${workspace.id}`}>Open</Link>
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
