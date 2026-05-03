"use client";

import { useRef, useState } from "react";
import { Loader2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useUploadDPA } from "@/lib/hooks/use-data-lifecycle";

export function DPAUploadDialog({ tenantId }: { tenantId: string }) {
  const [open, setOpen] = useState(false);
  const [version, setVersion] = useState("");
  const [effectiveDate, setEffectiveDate] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const upload = useUploadDPA(tenantId);

  const handleSubmit = () => {
    const file = fileRef.current?.files?.[0];
    if (!file || !version || !effectiveDate) return;
    upload.mutate(
      { file, version, effective_date: effectiveDate },
      {
        onSuccess: () => {
          setVersion("");
          setEffectiveDate("");
          if (fileRef.current) fileRef.current.value = "";
          setOpen(false);
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Upload className="mr-2 h-4 w-4" />
          Upload DPA
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload tenant DPA</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <p className="text-muted-foreground">
            PDF up to 50&nbsp;MB. The file is virus-scanned, hashed, and stored
            encrypted in Vault.
          </p>
          <div className="space-y-1">
            <Label htmlFor="dpa-file">DPA PDF</Label>
            <Input id="dpa-file" type="file" accept="application/pdf" ref={fileRef} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="dpa-version">Version</Label>
            <Input
              id="dpa-version"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              placeholder="v1, v2.1, …"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="dpa-effective">Effective date</Label>
            <Input
              id="dpa-effective"
              type="date"
              value={effectiveDate}
              onChange={(e) => setEffectiveDate(e.target.value)}
            />
          </div>
          {upload.isError ? (
            <p className="text-sm text-destructive">
              {upload.error?.message ?? "Upload failed."}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={upload.isPending}>
            {upload.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Upload
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
