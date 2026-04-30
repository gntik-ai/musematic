"use client";

import { useState } from "react";
import { KeyRound } from "lucide-react";
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

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          <KeyRound className="h-4 w-4" />
          Rotate secret
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Rotate connector secret</DialogTitle>
          <DialogDescription>
            The value is write-only and should be submitted to the backend secret rotation endpoint.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="connector-secret">New secret</Label>
            <Input id="connector-secret" onChange={(event) => setSecret(event.target.value)} type="password" value={secret} />
          </div>
          <Button disabled={!secret} onClick={() => setOpen(false)}>Confirm rotation</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
