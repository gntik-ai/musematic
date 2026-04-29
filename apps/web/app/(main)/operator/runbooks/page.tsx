"use client";

import { useState } from "react";
import Link from "next/link";
import { Search } from "lucide-react";
import { RunbookStaleBadge } from "@/components/features/incident-response";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useRunbooks } from "@/lib/api/incidents";

export default function OperatorRunbooksPage() {
  const [query, setQuery] = useState("");
  const runbooks = useRunbooks(query);
  return (
    <section className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Search className="h-4 w-4" />
            Runbooks
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Input
            aria-label="Search runbooks"
            placeholder="Search by scenario"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </CardContent>
      </Card>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {runbooks.data?.map((runbook) => (
          <Card key={runbook.id}>
            <CardHeader>
              <CardTitle className="text-base">{runbook.title}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">{runbook.scenario}</p>
              <RunbookStaleBadge isStale={runbook.is_stale} />
              <Button asChild variant="outline">
                <Link href={`/operator/runbooks/${runbook.id}`}>Open</Link>
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
      {!runbooks.isPending && !runbooks.data?.length ? (
        <EmptyState title="No runbooks" description="No runbooks match the current search." />
      ) : null}
    </section>
  );
}
