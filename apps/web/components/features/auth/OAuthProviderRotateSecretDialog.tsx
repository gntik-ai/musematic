"use client";

import { useState } from "react";
import { KeyRound, Loader2 } from "lucide-react";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/lib/hooks/use-toast";
import { useOAuthRotateSecretMutation } from "@/lib/hooks/use-oauth";
import type { OAuthProviderType } from "@/lib/types/oauth";

export function OAuthProviderRotateSecretDialog({
  providerType,
}: {
  providerType: OAuthProviderType;
}) {
  const t = useTranslations("admin.oauth");
  const { toast } = useToast();
  const mutation = useOAuthRotateSecretMutation(providerType);
  const [open, setOpen] = useState(false);
  const [newSecret, setNewSecret] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const canSubmit = newSecret.trim().length > 0 && confirmed && !mutation.isPending;

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen);
        if (!nextOpen) {
          setNewSecret("");
          setConfirmed(false);
        }
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          <KeyRound className="h-4 w-4" />
          {t("actions.rotateSecret")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("rotate.title")}</DialogTitle>
          <DialogDescription>{t("rotate.description")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor={`${providerType}-new-secret`}>{t("rotate.newSecret")}</Label>
            <Input
              autoComplete="new-password"
              id={`${providerType}-new-secret`}
              onChange={(event) => setNewSecret(event.target.value)}
              type="password"
              value={newSecret}
            />
          </div>
          <label className="flex items-start gap-3 text-sm">
            <Checkbox
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            <span>{t("rotate.confirmation")}</span>
          </label>
        </div>
        <DialogFooter>
          <Button onClick={() => setOpen(false)} variant="outline">
            {t("actions.cancel")}
          </Button>
          <Button
            disabled={!canSubmit}
            onClick={async () => {
              try {
                await mutation.mutateAsync(newSecret);
                toast({ title: t("rotate.success"), variant: "success" });
                setOpen(false);
              } catch (error) {
                toast({
                  title: t("rotate.failure"),
                  description: error instanceof Error ? error.message : undefined,
                  variant: "destructive",
                });
              }
            }}
          >
            {mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {t("actions.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
