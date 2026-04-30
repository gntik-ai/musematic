"use client";

import Link from "next/link";
import { Building2, ChevronRight } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspaces } from "@/lib/hooks/use-workspaces";

export default function WorkspacesPage() {
  const { workspaces, isLoading, isError } = useWorkspaces();

  if (isLoading) {
    return (
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <Skeleton key={index} className="h-36 rounded-lg" />
        ))}
      </section>
    );
  }

  if (isError) {
    return <EmptyState icon={Building2} title="Workspaces unavailable" description="The workspace list could not be loaded." />;
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-2 border-b pb-5">
        <Badge className="w-fit" variant="outline">Workspace owner</Badge>
        <h1 className="text-2xl font-semibold tracking-tight">Workspaces</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Open a workspace workbench for dashboard, members, settings, connectors, quotas, tags, and visibility.
        </p>
      </div>
      {workspaces.length ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {workspaces.map((workspace) => (
            <Card key={workspace.id}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Building2 className="h-4 w-4" />
                  {workspace.name}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="line-clamp-2 min-h-10 text-sm text-muted-foreground">
                  {workspace.description ?? "Workspace owner workbench"}
                </p>
                <Button asChild className="w-full" size="sm">
                  <Link href={`/workspaces/${workspace.id}`}>
                    Open
                    <ChevronRight className="h-4 w-4" />
                  </Link>
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState icon={Building2} title="No workspaces" description="No workspace memberships were returned." />
      )}
    </section>
  );
}
