"use client";

import { useState } from "react";
import { AlertTriangle, Loader2, ShieldAlert } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  useRequestTenantDeletion,
  useTenantDeletionJob,
} from "@/lib/hooks/use-data-lifecycle";

interface Props {
  tenantId: string;
  tenantSlug: string;
}

export function TenantDeletionPanel({ tenantId, tenantSlug }: Props) {
  const [typed, setTyped] = useState("");
  const [reason, setReason] = useState("");
  const [graceDays, setGraceDays] = useState(30);
  const [includeFinalExport, setIncludeFinalExport] = useState(true);
  const [twoPaToken, setTwoPaToken] = useState("");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  const requestDeletion = useRequestTenantDeletion(tenantId);
  const job = useTenantDeletionJob(tenantId, activeJobId);

  const matches = typed.trim() === tenantSlug;
  const submitted = requestDeletion.data ?? job.data ?? null;
  const canSubmit = matches && reason.trim().length > 0 && twoPaToken.trim().length > 0;

  const handleSubmit = () => {
    requestDeletion.mutate(
      {
        body: {
          typed_confirmation: typed.trim(),
          reason: reason.trim(),
          include_final_export: includeFinalExport,
          grace_period_days: graceDays,
        },
        twoPaToken: twoPaToken.trim(),
      },
      { onSuccess: (created) => setActiveJobId(created.id) },
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-destructive">
          <ShieldAlert className="h-5 w-5" />
          Tenant deletion
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Cascade reach</AlertTitle>
          <AlertDescription>
            Phase 2 cascades workspaces, users, agents, executions, audit chain
            (cold storage retained 7 years), Vault paths, DNS records, TLS
            certs, and OAuth callbacks. The tenant admin can recover during the
            grace period only.
          </AlertDescription>
        </Alert>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="typed">
              Type tenant slug{" "}
              <span className="font-mono font-semibold">{tenantSlug}</span>
            </Label>
            <Input
              id="typed"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="grace-days">Grace period (days)</Label>
            <Input
              id="grace-days"
              type="number"
              min={1}
              max={90}
              value={graceDays}
              onChange={(e) => setGraceDays(Number(e.target.value))}
            />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label htmlFor="reason">Reason (required, audit logged)</Label>
            <Textarea
              id="reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
            />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label htmlFor="2pa-token">Consumed 2PA token</Label>
            <Input
              id="2pa-token"
              value={twoPaToken}
              onChange={(e) => setTwoPaToken(e.target.value)}
              placeholder="Paste the consume_token from your 2PA challenge"
              autoComplete="off"
            />
          </div>
          <label className="flex items-center gap-2 md:col-span-2">
            <input
              type="checkbox"
              checked={includeFinalExport}
              onChange={(e) => setIncludeFinalExport(e.target.checked)}
            />
            <span>Generate final tenant export before cascade</span>
          </label>
        </div>

        {requestDeletion.isError ? (
          <Alert variant="destructive">
            <AlertTitle>Could not schedule deletion</AlertTitle>
            <AlertDescription>
              {requestDeletion.error?.message ?? "Please try again."}
            </AlertDescription>
          </Alert>
        ) : null}

        <Button
          variant="destructive"
          onClick={handleSubmit}
          disabled={!canSubmit || requestDeletion.isPending || Boolean(submitted)}
        >
          {requestDeletion.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : null}
          Schedule tenant deletion
        </Button>

        {submitted ? (
          <Alert>
            <AlertTitle>Deletion job created</AlertTitle>
            <AlertDescription>
              <div className="flex items-center gap-2">
                <Badge>{submitted.phase}</Badge>
                <span>
                  Grace ends at{" "}
                  {new Date(submitted.grace_ends_at).toLocaleString()}.
                </span>
              </div>
            </AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}
