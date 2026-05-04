"use client";

import { useState } from "react";
import { Eye, EyeOff, KeyRound, ShieldCheck } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

export interface TenantExportPasswordPayload {
  delivery_channel: "email" | "sms" | "vault" | null;
  delivery_status: "pending" | "delivered" | "failed" | null;
  delivered_at: string | null;
  recipient_hint: string | null;
  password_revealed: boolean;
  password?: string | null;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  payload: TenantExportPasswordPayload | null;
  trigger?: React.ReactNode;
}

export function TenantExportPasswordDialog({
  open,
  onOpenChange,
  payload,
  trigger,
}: Props) {
  const [showPassword, setShowPassword] = useState(false);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {trigger ? <DialogTrigger asChild>{trigger}</DialogTrigger> : null}
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5" />
            Tenant export password
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 text-sm">
          <Alert>
            <KeyRound className="h-4 w-4" />
            <AlertTitle>Out-of-band delivery</AlertTitle>
            <AlertDescription>
              The download password is delivered to the tenant admin through a
              separate channel from the URL. Only the tenant admin can open the
              archive.
            </AlertDescription>
          </Alert>

          {payload ? (
            <div className="space-y-2 rounded-md border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs uppercase tracking-wide text-muted-foreground">
                  Channel
                </span>
                <Badge variant="secondary">
                  {payload.delivery_channel ?? "unconfigured"}
                </Badge>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs uppercase tracking-wide text-muted-foreground">
                  Status
                </span>
                <Badge>{payload.delivery_status ?? "unknown"}</Badge>
              </div>
              {payload.delivered_at ? (
                <p className="text-xs text-muted-foreground">
                  Delivered at {new Date(payload.delivered_at).toLocaleString()}
                </p>
              ) : null}
              {payload.recipient_hint ? (
                <p className="text-xs text-muted-foreground">
                  Recipient hint:{" "}
                  <span className="font-mono">{payload.recipient_hint}</span>
                </p>
              ) : null}
            </div>
          ) : null}

          {payload?.password_revealed && payload.password ? (
            <div className="space-y-2 rounded-md border border-amber-300 bg-amber-50 p-3 dark:bg-amber-950/40">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-amber-900 dark:text-amber-200">
                  Password (reveal once)
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowPassword((s) => !s)}
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </Button>
              </div>
              <p className="break-all font-mono text-sm">
                {showPassword ? payload.password : "•".repeat(payload.password.length)}
              </p>
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
