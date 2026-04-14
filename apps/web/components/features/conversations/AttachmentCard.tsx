"use client";

import { useState } from "react";
import { FileCode2, FileImage, FileText } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog";
import type { MessageAttachment } from "@/types/conversations";

function getAttachmentIcon(attachment: MessageAttachment) {
  if (
    attachment.mime_type.includes("json") ||
    attachment.mime_type.includes("javascript") ||
    attachment.mime_type.includes("typescript")
  ) {
    return FileCode2;
  }

  return FileText;
}

function formatBytes(sizeBytes: number) {
  return new Intl.NumberFormat("en", {
    maximumFractionDigits: 1,
    notation: sizeBytes > 1_000_000 ? "compact" : "standard",
  }).format(sizeBytes);
}

export function AttachmentCard({
  attachment,
}: {
  attachment: MessageAttachment;
}) {
  if (attachment.mime_type.startsWith("image/")) {
    return <ImageAttachmentCard attachment={attachment} />;
  }

  const Icon = getAttachmentIcon(attachment);

  return (
    <a
      className="flex items-center gap-3 rounded-xl border border-border bg-card/70 px-4 py-3 text-sm transition-colors hover:bg-accent/30"
      download
      href={attachment.url}
      rel="noreferrer"
      target="_blank"
    >
      <Icon className="h-5 w-5 text-muted-foreground" />
      <div className="min-w-0">
        <p className="truncate font-medium">{attachment.filename}</p>
        <p className="text-xs text-muted-foreground">
          {attachment.mime_type} · {formatBytes(attachment.size_bytes)} bytes
        </p>
      </div>
    </a>
  );
}

function ImageAttachmentCard({
  attachment,
}: {
  attachment: MessageAttachment;
}) {
  const [open, setOpen] = useState(false);

  return (
    <Dialog onOpenChange={setOpen} open={open}>
      <div className="space-y-2">
        <DialogTitle className="sr-only">{attachment.filename}</DialogTitle>
        <button
          className="block overflow-hidden rounded-xl border border-border"
          onClick={() => setOpen(true)}
          type="button"
        >
          <img
            alt={attachment.filename}
            className="max-h-64 w-full object-cover"
            src={attachment.url}
          />
        </button>
      </div>
      <DialogContent className="max-w-4xl p-0">
        <img
          alt={attachment.filename}
          className="max-h-[80vh] w-full object-contain"
          src={attachment.url}
        />
      </DialogContent>
    </Dialog>
  );
}
