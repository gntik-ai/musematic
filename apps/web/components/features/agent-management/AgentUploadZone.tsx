"use client";

import { useRef, useState } from "react";
import { AlertCircle, UploadCloud, XCircle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { navigateToAgentDetail } from "@/lib/agent-management/navigation";
import { useUploadAgentPackage, UploadValidationError } from "@/lib/hooks/use-agent-upload";
import { useToast } from "@/lib/hooks/use-toast";
import { ApiError } from "@/types/api";

const ACCEPTED_EXTENSIONS = [".tar.gz", ".zip"];
const ACCEPTED_MIME_TYPES = [
  "application/gzip",
  "application/x-gzip",
  "application/zip",
  "application/x-zip-compressed",
  "application/octet-stream",
];

export interface AgentUploadZoneProps {
  workspace_id: string;
  onUploadComplete: (fqn: string) => void;
}

function isValidFile(file: File): boolean {
  const normalizedName = file.name.toLowerCase();
  const validExtension = ACCEPTED_EXTENSIONS.some((extension) =>
    normalizedName.endsWith(extension),
  );

  return validExtension && ACCEPTED_MIME_TYPES.includes(file.type || "application/octet-stream");
}

export function AgentUploadZone({
  workspace_id,
  onUploadComplete,
}: AgentUploadZoneProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const uploadMutation = useUploadAgentPackage();
  const { toast } = useToast();
  const [dragActive, setDragActive] = useState(false);
  const [clientError, setClientError] = useState<string | null>(null);

  const handleFile = async (file: File | null) => {
    if (!file) {
      return;
    }

    if (!isValidFile(file)) {
      setClientError("Unsupported file type. Only .tar.gz and .zip files are accepted.");
      return;
    }

    setClientError(null);

    try {
      const response = await uploadMutation.mutateAsync({
        file,
        workspaceId: workspace_id,
      });
      toast({
        title: "Agent uploaded",
        description: `${response.agent_fqn} is ready as a draft.`,
        variant: "success",
      });
      onUploadComplete(response.agent_fqn);
      navigateToAgentDetail(response.agent_fqn);
    } catch (error) {
      if (error instanceof UploadValidationError) {
        return;
      }

      toast({
        title: error instanceof ApiError ? error.message : "Upload failed",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="space-y-4">
      <div
        className={[
          "rounded-3xl border border-dashed p-8 text-center transition-colors",
          dragActive
            ? "border-brand-accent bg-brand-accent/5"
            : "border-border/60 bg-card/70",
        ].join(" ")}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          if (event.currentTarget.contains(event.relatedTarget as Node | null)) {
            return;
          }
          setDragActive(false);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setDragActive(true);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragActive(false);
          void handleFile(event.dataTransfer.files?.[0] ?? null);
        }}
      >
        <UploadCloud className="mx-auto h-10 w-10 text-brand-accent" />
        <h3 className="mt-4 text-lg font-semibold">Drop an agent package here</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Upload a <code>.tar.gz</code> or <code>.zip</code> package to create a draft agent.
        </p>
        <Input
          ref={inputRef}
          accept=".tar.gz,.zip"
          aria-label="Select package"
          className="hidden"
          tabIndex={-1}
          type="file"
          onChange={(event) => {
            void handleFile(event.currentTarget.files?.[0] ?? null);
          }}
        />
        <Button
          className="mt-4"
          type="button"
          variant="outline"
          onClick={() => inputRef.current?.click()}
        >
          Select package
        </Button>
      </div>

      {clientError ? (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Upload blocked</AlertTitle>
          <AlertDescription>{clientError}</AlertDescription>
        </Alert>
      ) : null}

      {uploadMutation.validationErrors.length > 0 ? (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Validation errors</AlertTitle>
          <AlertDescription>
            {uploadMutation.validationErrors.join(" ")}
          </AlertDescription>
        </Alert>
      ) : null}

      {uploadMutation.isPending ? (
        <div className="space-y-3 rounded-2xl border border-border/60 bg-background/70 p-4">
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="font-medium">Uploading package…</span>
            <span>{uploadMutation.progress}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-brand-accent transition-[width]"
              style={{ width: `${uploadMutation.progress}%` }}
            />
          </div>
          <Button
            className="gap-2"
            type="button"
            variant="ghost"
            onClick={() => uploadMutation.abort()}
          >
            <XCircle className="h-4 w-4" />
            Cancel upload
          </Button>
        </div>
      ) : null}
    </div>
  );
}
