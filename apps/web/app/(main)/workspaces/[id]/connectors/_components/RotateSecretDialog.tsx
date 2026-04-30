"use client";

import { useState } from "react";
import { KeyRound } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function RotateSecretDialog() {
  const [open, setOpen] = useState(false);
  const [secret, setSecret] = useState("");
  const t = useTranslations("workspaces.connectors.rotate");

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          <KeyRound className="h-4 w-4" />
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
        <div className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="connector-secret">{t("newSecret")}</Label>
            <Input id="connector-secret" onChange={(event) => setSecret(event.target.value)} type="password" value={secret} />
          </div>
          <Button disabled={!secret} onClick={() => setOpen(false)}>{t("confirm")}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
