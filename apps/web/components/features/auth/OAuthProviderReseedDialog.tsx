"use client";

import { useMemo, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/lib/hooks/use-toast";
import { useOAuthReseedMutation } from "@/lib/hooks/use-oauth";
import type { OAuthProviderType } from "@/lib/types/oauth";

export function OAuthProviderReseedDialog({
  providerType,
}: {
  providerType: OAuthProviderType;
}) {
  const t = useTranslations("admin.oauth");
  const { toast } = useToast();
  const mutation = useOAuthReseedMutation(providerType);
  const [open, setOpen] = useState(false);
  const [forceUpdate, setForceUpdate] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const changedFields = useMemo(() => {
    const raw = mutation.data?.diff.changed_fields;
    if (!raw || typeof raw !== "object") {
      return [];
    }
    return Object.keys(raw);
  }, [mutation.data?.diff.changed_fields]);

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen);
        if (!nextOpen) {
          setForceUpdate(false);
          setAcknowledged(false);
          mutation.reset();
        }
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          <RefreshCw className="h-4 w-4" />
          {t("actions.reseed")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("reseed.title")}</DialogTitle>
          <DialogDescription>{t("reseed.description")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <label className="flex items-start gap-3 text-sm">
            <Checkbox
              checked={acknowledged}
              onChange={(event) => setAcknowledged(event.target.checked)}
            />
            <span>{t("reseed.acknowledge")}</span>
          </label>
          <div className="flex items-center justify-between rounded-md border border-border p-3">
            <div>
              <Label htmlFor={`${providerType}-force-update`}>
                {t("reseed.forceUpdate")}
              </Label>
              <p className="text-sm text-muted-foreground">
                {t("reseed.forceUpdateHelp")}
              </p>
            </div>
            <Switch
              checked={forceUpdate}
              id={`${providerType}-force-update`}
              onCheckedChange={setForceUpdate}
            />
          </div>
          {changedFields.length > 0 ? (
            <div className="rounded-md border border-border p-3 text-sm">
              <p className="font-medium">{t("reseed.changedFields")}</p>
              <ul className="mt-2 space-y-1 text-muted-foreground">
                {changedFields.map((field) => (
                  <li key={field}>{field}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button onClick={() => setOpen(false)} variant="outline">
            {t("actions.cancel")}
          </Button>
          <Button
            disabled={!acknowledged || mutation.isPending}
            onClick={async () => {
              try {
                await mutation.mutateAsync(forceUpdate);
                toast({ title: t("reseed.success"), variant: "success" });
              } catch (error) {
                toast({
                  title: t("reseed.failure"),
                  description: error instanceof Error ? error.message : undefined,
                  variant: "destructive",
                });
              }
            }}
          >
            {mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {t("actions.apply")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
