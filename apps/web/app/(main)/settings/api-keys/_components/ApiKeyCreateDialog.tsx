"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
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
import { Textarea } from "@/components/ui/textarea";
import { useCreateApiKey } from "@/lib/hooks/use-me-api-keys";
import type { UserServiceAccountCreateResponse } from "@/lib/schemas/me";

interface ApiKeyCreateDialogProps {
  disabled: boolean;
  onCreated: (response: UserServiceAccountCreateResponse) => void;
}

export function ApiKeyCreateDialog({ disabled, onCreated }: ApiKeyCreateDialogProps) {
  const t = useTranslations("apiKeys.create");
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState("agents:read");
  const [expiresAt, setExpiresAt] = useState("");
  const [mfaToken, setMfaToken] = useState("");
  const createApiKey = useCreateApiKey();

  function submit() {
    createApiKey.mutate(
      {
        name,
        scopes: scopes
          .split(/[\n,]/)
          .map((scope) => scope.trim())
          .filter(Boolean),
        expires_at: expiresAt ? new Date(`${expiresAt}T23:59:59`).toISOString() : null,
        mfa_token: mfaToken || null,
      },
      {
        onSuccess: (response) => {
          onCreated(response);
          setName("");
          setScopes("agents:read");
          setExpiresAt("");
          setMfaToken("");
          setOpen(false);
        },
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button disabled={disabled}>
          <Plus className="h-4 w-4" />
          {t("trigger")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>
            {t("description")}
          </DialogDescription>
        </DialogHeader>
        <div className="mt-4 space-y-4">
          <div className="space-y-2">
            <Label htmlFor="api-key-name">{t("name")}</Label>
            <Input
              id="api-key-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="api-key-scopes">{t("scopes")}</Label>
            <Textarea
              id="api-key-scopes"
              value={scopes}
              onChange={(event) => setScopes(event.target.value)}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="api-key-expiry">{t("expires")}</Label>
              <Input
                id="api-key-expiry"
                type="date"
                value={expiresAt}
                onChange={(event) => setExpiresAt(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="api-key-mfa">{t("mfaCode")}</Label>
              <Input
                id="api-key-mfa"
                inputMode="numeric"
                value={mfaToken}
                onChange={(event) => setMfaToken(event.target.value)}
              />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => setOpen(false)}
          >
            {t("cancel")}
          </Button>
          <Button disabled={!name || createApiKey.isPending} onClick={submit}>
            {t("submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
