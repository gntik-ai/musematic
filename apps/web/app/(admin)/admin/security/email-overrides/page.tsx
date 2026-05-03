"use client";

/**
 * UPD-050 T045 — Disposable-email override list admin page.
 *
 * Per `quickstart.md` Walkthrough 2 — super admin can add/remove
 * domain-level overrides that take precedence over the upstream
 * disposable-email blocklist, and trigger a manual upstream refresh.
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useAddDisposableEmailOverride,
  useDisposableEmailOverrides,
  useRefreshBlocklist,
  useRemoveDisposableEmailOverride,
} from "@/lib/hooks/use-disposable-email-overrides";

export default function EmailOverridesPage() {
  const overridesQuery = useDisposableEmailOverrides();
  const addOverride = useAddDisposableEmailOverride();
  const removeOverride = useRemoveDisposableEmailOverride();
  const refreshBlocklist = useRefreshBlocklist();
  const [domain, setDomain] = useState("");
  const [mode, setMode] = useState<"allow" | "block">("allow");
  const [reason, setReason] = useState("");

  const onAdd = async () => {
    if (!domain.trim()) return;
    await addOverride.mutateAsync({
      domain: domain.trim().toLowerCase(),
      mode,
      reason: reason.trim() || undefined,
    });
    setDomain("");
    setReason("");
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-normal">
            Disposable-email overrides
          </h1>
          <p className="text-sm text-muted-foreground">
            Per-domain overrides that take precedence over the weekly
            upstream blocklist. Allow-overrides un-block legitimate
            domains; block-overrides force-block domains the upstream
            list misses.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => refreshBlocklist.mutate()}
          disabled={refreshBlocklist.isPending}
        >
          Refresh blocklist now
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Add override</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-[1fr_auto_1fr_auto]">
          <div>
            <Label htmlFor="domain">Domain</Label>
            <Input
              id="domain"
              placeholder="example.com"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              data-testid="email-override-domain-input"
            />
          </div>
          <div>
            <Label>Mode</Label>
            <select
              className="block h-10 w-32 rounded-md border bg-background px-3"
              value={mode}
              onChange={(e) => setMode(e.target.value as "allow" | "block")}
              data-testid="email-override-mode-select"
            >
              <option value="allow">Allow</option>
              <option value="block">Block</option>
            </select>
          </div>
          <div>
            <Label htmlFor="reason">Reason</Label>
            <Input
              id="reason"
              placeholder="Confirmed by support ticket #..."
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>
          <Button
            className="self-end"
            onClick={onAdd}
            disabled={addOverride.isPending || !domain.trim()}
            data-testid="email-override-add-button"
          >
            Add
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Current overrides</CardTitle>
        </CardHeader>
        <CardContent>
          {overridesQuery.isLoading ? (
            <Skeleton className="h-20 w-full" />
          ) : overridesQuery.isError ? (
            <p className="text-sm text-destructive">Could not load overrides.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Domain</TableHead>
                  <TableHead>Mode</TableHead>
                  <TableHead>Reason</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(overridesQuery.data?.items ?? []).map((o) => (
                  <TableRow key={o.domain}>
                    <TableCell className="font-mono">{o.domain}</TableCell>
                    <TableCell>
                      <Badge
                        variant={o.mode === "allow" ? "outline" : "destructive"}
                      >
                        {o.mode}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {o.reason ?? "—"}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {new Date(o.created_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => removeOverride.mutate(o.domain)}
                        disabled={removeOverride.isPending}
                      >
                        Remove
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
