"use client";

import { useState } from "react";
import { Download, Upload } from "lucide-react";
import { AdminPage } from "@/components/features/admin/AdminPage";
import { AdminWriteButton } from "@/components/features/admin/AdminWriteButton";
import { ChangePreview } from "@/components/features/admin/ChangePreview";
import { ConfirmationDialog } from "@/components/features/admin/ConfirmationDialog";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/store/auth-store";

interface ImportPreview {
  valid_signature: boolean;
  bundle_hash: string;
  diffs: Array<{ action: string; resource: string }>;
}

export default function InstallerPage() {
  const accessToken = useAuthStore((state) => state.accessToken);
  const [bundle, setBundle] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  async function authFetch(path: string, init: RequestInit) {
    const headers = new Headers(init.headers);
    if (accessToken) {
      headers.set("Authorization", `Bearer ${accessToken}`);
    }
    const response = await fetch(`${apiBaseUrl}${path}`, { ...init, headers });
    if (!response.ok) {
      throw new Error(`Admin config request failed: ${response.status}`);
    }
    return response;
  }

  async function exportConfig() {
    const response = await authFetch("/api/v1/admin/config/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scope: "platform" }),
    });
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "musematic-config.tar.gz";
    link.click();
    URL.revokeObjectURL(url);
  }

  async function previewImport(nextBundle = bundle) {
    if (!nextBundle) {
      return;
    }
    const formData = new FormData();
    formData.append("bundle", nextBundle);
    const response = await authFetch("/api/v1/admin/config/import/preview", {
      method: "POST",
      body: formData,
    });
    setPreview((await response.json()) as ImportPreview);
  }

  async function applyImport() {
    if (!bundle) {
      return;
    }
    const formData = new FormData();
    formData.append("confirmation_phrase", "IMPORT CONFIG");
    formData.append("bundle", bundle);
    await authFetch("/api/v1/admin/config/import/apply", {
      method: "POST",
      body: formData,
    });
    setConfirmOpen(false);
  }

  return (
    <AdminPage
      title="Installer"
      description="Installer state and configuration import/export."
      actions={
        <AdminWriteButton size="sm" onClick={() => void exportConfig()}>
          <Download className="h-4 w-4" />
          Export configuration
        </AdminWriteButton>
      }
      help={<p>Export signed configuration bundles and preview imports before applying them.</p>}
    >
      <div className="space-y-4">
        <div className="grid gap-3 rounded-md border bg-card p-4 sm:grid-cols-3">
          <div>
            <div className="text-sm font-medium">Install method</div>
            <div className="text-sm text-muted-foreground">Headless bootstrap</div>
          </div>
          <div>
            <div className="text-sm font-medium">Secret handling</div>
            <div className="text-sm text-muted-foreground">Secrets omitted from bundles</div>
          </div>
          <div>
            <div className="text-sm font-medium">Audit</div>
            <div className="text-sm text-muted-foreground">Export and import are signed</div>
          </div>
        </div>
        <div className="rounded-md border bg-card p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <Input
              type="file"
              accept=".tar,.tar.gz,.tgz,.yaml,.yml"
              onChange={(event) => {
                const nextBundle = event.target.files?.[0] ?? null;
                setBundle(nextBundle);
                setPreview(null);
                if (nextBundle) {
                  void previewImport(nextBundle);
                }
              }}
            />
            <AdminWriteButton disabled={!preview} onClick={() => setConfirmOpen(true)}>
              <Upload className="h-4 w-4" />
              Import configuration
            </AdminWriteButton>
          </div>
          {preview ? (
            <div className="mt-4 space-y-3">
              <ChangePreview
                affectedCount={preview.diffs.length}
                irreversibility="partially_reversible"
                estimatedDuration="Under 1 minute"
                implications={[
                  preview.valid_signature ? "Signature verified" : "Signature invalid",
                  `Bundle ${preview.bundle_hash.slice(0, 12)}`,
                ]}
              />
              <div className="text-sm text-muted-foreground">
                {preview.diffs.length} configuration resources will be created, updated, or left unchanged.
              </div>
            </div>
          ) : null}
        </div>
      </div>
      <ConfirmationDialog
        open={confirmOpen}
        variant="typed"
        title="Import configuration"
        phrase="IMPORT CONFIG"
        onOpenChange={setConfirmOpen}
        onConfirm={() => void applyImport()}
      />
    </AdminPage>
  );
}
