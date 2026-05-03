"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { CalendarClock, Edit3, Loader2, PauseCircle, Save, Trash2 } from "lucide-react";
import { AdminWriteButton } from "@/components/features/admin/AdminWriteButton";
import { DeletionGracePeriodCountdown } from "@/components/features/admin/DeletionGracePeriodCountdown";
import { TenantBrandingPreview } from "@/components/features/admin/TenantBrandingPreview";
import { TenantStatusBadge } from "@/components/features/admin/TenantStatusBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAdminTenant,
  useUpdateTenant,
  useCancelTenantDeletion,
  useReactivateTenant,
  useScheduleTenantDeletion,
  useSuspendTenant,
  type TenantAdminView,
  type TenantRegion,
} from "@/lib/hooks/use-admin-tenants";
import { toast } from "@/lib/hooks/use-toast";
import { getInitials } from "@/lib/utils";

const TENANT_REGION_VALUES = ["global", "eu-central", "us-east", "us-west"] as const;

function formatDate(value?: string | null): string {
  if (!value) {
    return "None";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "None";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function metadataEntries(record: Record<string, unknown>): Array<[string, string]> {
  return Object.entries(record).map(([key, value]) => [key, displayValue(value)]);
}

function tenantHost(tenant: TenantAdminView): string {
  return `${tenant.subdomain}.musematic.ai`;
}

function errorMessage(error: unknown): string | null {
  if (!error) {
    return null;
  }
  return error instanceof Error ? error.message : "Tenant update failed";
}

export function TenantDetailPanel({ tenantId }: { tenantId: string }) {
  const { data: tenant, error, isLoading } = useAdminTenant(tenantId);
  const updateTenant = useUpdateTenant();
  const suspendTenant = useSuspendTenant();
  const reactivateTenant = useReactivateTenant();
  const scheduleDeletion = useScheduleTenantDeletion();
  const cancelDeletion = useCancelTenantDeletion();
  const [editing, setEditing] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [region, setRegion] = useState<TenantRegion>("eu-central");
  const [logoUrl, setLogoUrl] = useState("");
  const [accentColor, setAccentColor] = useState("");

  useEffect(() => {
    if (!tenant) {
      return;
    }
    setDisplayName(tenant.display_name);
    setRegion(
      TENANT_REGION_VALUES.includes(tenant.region as TenantRegion)
        ? (tenant.region as TenantRegion)
        : "eu-central",
    );
    setLogoUrl(tenant.branding.logo_url ?? "");
    setAccentColor(tenant.branding.accent_color_hex ?? "");
  }, [tenant]);

  const contractMetadata = useMemo(
    () => metadataEntries(tenant?.contract_metadata ?? {}),
    [tenant?.contract_metadata],
  );
  const featureFlags = useMemo(
    () => metadataEntries(tenant?.feature_flags ?? {}),
    [tenant?.feature_flags],
  );
  const updateError = errorMessage(updateTenant.error);
  const isDefaultTenant = tenant?.kind === "default";

  async function suspend() {
    if (!tenant) {
      return;
    }
    const reason = window.prompt("Suspend reason");
    if (!reason) {
      return;
    }
    await suspendTenant.mutateAsync({ id: tenant.id, payload: { reason } });
    toast({ title: "Tenant suspended", variant: "success" });
  }

  async function reactivate() {
    if (!tenant) {
      return;
    }
    await reactivateTenant.mutateAsync(tenant.id);
    toast({ title: "Tenant reactivated", variant: "success" });
  }

  async function scheduleDeletionAction() {
    if (!tenant) {
      return;
    }
    const reason = window.prompt("Deletion reason");
    const twoPaToken = window.prompt("2PA token");
    if (!reason || !twoPaToken) {
      return;
    }
    await scheduleDeletion.mutateAsync({
      id: tenant.id,
      payload: { reason, two_pa_token: twoPaToken },
    });
    toast({ title: "Tenant deletion scheduled", variant: "success" });
  }

  async function cancelDeletionAction() {
    if (!tenant) {
      return;
    }
    await cancelDeletion.mutateAsync(tenant.id);
    toast({ title: "Tenant deletion cancelled", variant: "success" });
  }

  async function saveChanges() {
    if (!tenant) {
      return;
    }
    await updateTenant.mutateAsync({
      id: tenant.id,
      payload: {
        display_name: displayName.trim(),
        region,
        branding_config: {
          ...tenant.branding,
          logo_url: logoUrl.trim() || null,
          accent_color_hex: accentColor.trim() || null,
        },
      },
    });
    toast({ title: "Tenant updated", variant: "success" });
    setEditing(false);
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full" />
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      </div>
    );
  }

  if (error || !tenant) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Tenant unavailable</AlertTitle>
        <AlertDescription>{errorMessage(error) ?? "Tenant was not found"}</AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-4">
      {updateError ? (
        <Alert variant="destructive">
          <AlertTitle>Update failed</AlertTitle>
          <AlertDescription>{updateError}</AlertDescription>
        </Alert>
      ) : null}

      <section className="rounded-md border bg-card p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex min-w-0 gap-4">
            <div
              className="flex h-14 w-14 shrink-0 items-center justify-center rounded-md border text-sm font-semibold"
              style={{ borderColor: tenant.branding.accent_color_hex ?? undefined }}
            >
              {tenant.branding.logo_url ? (
                <img
                  alt=""
                  className="max-h-10 max-w-10 object-contain"
                  src={tenant.branding.logo_url}
                />
              ) : (
                getInitials(tenant.display_name)
              )}
            </div>
            <div className="min-w-0">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <TenantStatusBadge status={tenant.status} />
                <span className="rounded-md border px-2 py-0.5 text-xs text-muted-foreground">
                  {tenant.kind}
                </span>
              </div>
              <h2 className="truncate text-xl font-semibold tracking-normal">
                {tenant.display_name}
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {tenant.slug} · {tenantHost(tenant)}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm">
              <Link href="/admin/tenants">Back</Link>
            </Button>
            <AdminWriteButton
              size="sm"
              variant="outline"
              onClick={() => setEditing((current) => !current)}
            >
              <Edit3 className="h-4 w-4" />
              Edit
            </AdminWriteButton>
            <AdminWriteButton
              disabled={isDefaultTenant}
              size="sm"
              variant="outline"
              title={
                isDefaultTenant
                  ? "The default tenant is immutable by SaaS-9."
                  : "Suspend tenant access"
              }
              onClick={tenant.status === "suspended" ? reactivate : suspend}
            >
              <PauseCircle className="h-4 w-4" />
              {tenant.status === "suspended" ? "Reactivate" : "Suspend"}
            </AdminWriteButton>
            <AdminWriteButton
              disabled={isDefaultTenant}
              size="sm"
              variant="destructive"
              title={
                isDefaultTenant
                  ? "The default tenant is immutable by SaaS-9."
                  : "Schedule deletion"
              }
              onClick={scheduleDeletionAction}
            >
              <Trash2 className="h-4 w-4" />
              Schedule deletion
            </AdminWriteButton>
          </div>
        </div>
      </section>

      {tenant.status === "pending_deletion" ? (
        <DeletionGracePeriodCountdown
          disabled={cancelDeletion.isPending}
          onCancel={cancelDeletionAction}
          scheduledDeletionAt={tenant.scheduled_deletion_at}
        />
      ) : null}

      {editing ? (
        <section className="rounded-md border bg-card p-5">
          <div className="grid gap-4 lg:grid-cols-2">
            <label className="space-y-2 text-sm font-medium">
              Display name
              <Input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
              />
            </label>
            <label className="space-y-2 text-sm font-medium">
              Region
              <Select
                value={region}
                onChange={(event) => setRegion(event.target.value as TenantRegion)}
              >
                {TENANT_REGION_VALUES.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </Select>
            </label>
            <label className="space-y-2 text-sm font-medium">
              Logo URL
              <Input
                value={logoUrl}
                onChange={(event) => setLogoUrl(event.target.value)}
              />
            </label>
            <label className="space-y-2 text-sm font-medium">
              Accent color
              <div className="flex gap-2">
                <Input
                  value={accentColor}
                  onChange={(event) => setAccentColor(event.target.value)}
                />
                <input
                  aria-label="Accent color picker"
                  className="h-10 w-12 rounded-md border bg-background"
                  type="color"
                  value={accentColor || "#0078d4"}
                  onChange={(event) => setAccentColor(event.target.value)}
                />
              </div>
            </label>
          </div>
          <div className="mt-4 flex justify-end">
            <AdminWriteButton
              disabled={updateTenant.isPending}
              disabledByMaintenance
              onClick={saveChanges}
              size="sm"
            >
              {updateTenant.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Save
            </AdminWriteButton>
          </div>
        </section>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <TenantBrandingPreview tenant={tenant} />
        <section className="rounded-md border bg-card p-5">
          <h3 className="text-base font-semibold tracking-normal">Tenant metrics</h3>
          <dl className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <dt className="text-xs uppercase text-muted-foreground">Members</dt>
              <dd className="mt-1 text-lg font-semibold">{tenant.member_count}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-muted-foreground">Workspaces</dt>
              <dd className="mt-1 text-lg font-semibold">
                {tenant.active_workspace_count}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-muted-foreground">Created</dt>
              <dd className="mt-1 text-sm">{formatDate(tenant.created_at)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-muted-foreground">Region</dt>
              <dd className="mt-1 text-sm">{tenant.region}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-muted-foreground">Isolation</dt>
              <dd className="mt-1 text-sm">{tenant.data_isolation_mode}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-muted-foreground">Deletion date</dt>
              <dd className="mt-1 text-sm">
                {formatDate(tenant.scheduled_deletion_at)}
              </dd>
            </div>
          </dl>
        </section>

        <section className="rounded-md border bg-card p-5">
          <h3 className="text-base font-semibold tracking-normal">DPA metadata</h3>
          <dl className="mt-4 space-y-3 text-sm">
            <div className="grid gap-1 sm:grid-cols-[130px_minmax(0,1fr)]">
              <dt className="text-muted-foreground">Signed</dt>
              <dd>{formatDate(tenant.dpa_signed_at)}</dd>
            </div>
            <div className="grid gap-1 sm:grid-cols-[130px_minmax(0,1fr)]">
              <dt className="text-muted-foreground">Version</dt>
              <dd>{displayValue(tenant.dpa_version)}</dd>
            </div>
            <div className="grid gap-1 sm:grid-cols-[130px_minmax(0,1fr)]">
              <dt className="text-muted-foreground">SHA-256</dt>
              <dd className="break-all font-mono text-xs">
                {displayValue(tenant.dpa_artifact_sha256)}
              </dd>
            </div>
            <div className="grid gap-1 sm:grid-cols-[130px_minmax(0,1fr)]">
              <dt className="text-muted-foreground">Artifact</dt>
              <dd className="break-all font-mono text-xs">
                {displayValue(tenant.dpa_artifact_uri)}
              </dd>
            </div>
          </dl>
        </section>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <section className="rounded-md border bg-card p-5">
          <h3 className="text-base font-semibold tracking-normal">Contract metadata</h3>
          <div className="mt-4 space-y-3 text-sm">
            {contractMetadata.length === 0 ? (
              <p className="text-muted-foreground">No contract metadata</p>
            ) : (
              contractMetadata.map(([key, value]) => (
                <div key={key} className="grid gap-1 sm:grid-cols-[160px_minmax(0,1fr)]">
                  <span className="text-muted-foreground">{key}</span>
                  <span className="break-words">{value}</span>
                </div>
              ))
            )}
          </div>
        </section>

        <section className="rounded-md border bg-card p-5">
          <h3 className="text-base font-semibold tracking-normal">Feature flags</h3>
          {/* UPD-049 refresh (102) — explicit toggle for the
              consume_public_marketplace flag (T039). Off-by-default
              for non-default tenants; only meaningful for Enterprise
              tenants per FR-741.1. */}
          {tenant.kind === "enterprise" ? (
            <ConsumePublicMarketplaceToggle
              tenantId={tenant.id}
              currentFlags={tenant.feature_flags ?? {}}
            />
          ) : null}
          <div className="mt-4 space-y-3 text-sm">
            {featureFlags.length === 0 ? (
              <p className="text-muted-foreground">No tenant flags</p>
            ) : (
              featureFlags.map(([key, value]) => (
                <div key={key} className="grid gap-1 sm:grid-cols-[160px_minmax(0,1fr)]">
                  <span className="text-muted-foreground">{key}</span>
                  <span className="break-words">{value}</span>
                </div>
              ))
            )}
          </div>
        </section>
      </div>

      <section className="rounded-md border bg-card p-5">
        <h3 className="flex items-center gap-2 text-base font-semibold tracking-normal">
          <CalendarClock className="h-4 w-4" />
          Lifecycle audit
        </h3>
        <div className="mt-4 space-y-3 text-sm">
          {(tenant.recent_lifecycle_audit_entries ?? []).length === 0 ? (
            <p className="text-muted-foreground">No lifecycle audit entries</p>
          ) : (
            tenant.recent_lifecycle_audit_entries?.map((entry) => (
              <div
                key={entry.id}
                className="grid gap-1 border-b pb-3 last:border-b-0 last:pb-0 sm:grid-cols-[220px_minmax(0,1fr)_120px]"
              >
                <span>{formatDate(entry.created_at)}</span>
                <span className="font-medium">{entry.event_type}</span>
                <span className="text-muted-foreground">{entry.actor_role ?? "unknown"}</span>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}


/**
 * UPD-049 refresh (102) T039 — toggle for the
 * `consume_public_marketplace` per-tenant feature flag. PATCHes the
 * tenant via `useUpdateTenant` with a merged feature_flags payload.
 *
 * Only renders for Enterprise tenants; default-tenant users always
 * have access to the public hub by virtue of being in the default
 * tenant.
 */
function ConsumePublicMarketplaceToggle({
  tenantId,
  currentFlags,
}: {
  tenantId: string;
  currentFlags: Record<string, unknown>;
}) {
  const updateTenant = useUpdateTenant();
  const consumeEnabled = Boolean(currentFlags["consume_public_marketplace"]);

  async function onToggle() {
    const next = {
      ...currentFlags,
      consume_public_marketplace: !consumeEnabled,
    };
    await updateTenant.mutateAsync({
      id: tenantId,
      payload: { feature_flags: next },
    });
    toast({
      title: consumeEnabled
        ? "Consume public marketplace disabled"
        : "Consume public marketplace enabled",
      variant: "success",
    });
  }

  return (
    <div className="mt-2 flex items-center justify-between gap-3 rounded-md border bg-background/40 p-3">
      <div className="min-w-0">
        <p className="text-sm font-medium">consume_public_marketplace</p>
        <p className="text-xs text-muted-foreground">
          When enabled, this tenant&apos;s users see public default-tenant
          marketplace agents alongside their own (read-only). Cost
          attribution is to the consuming tenant.
        </p>
      </div>
      <AdminWriteButton
        size="sm"
        variant={consumeEnabled ? "default" : "outline"}
        onClick={onToggle}
        disabled={updateTenant.isPending}
        data-testid="consume-public-marketplace-toggle"
        aria-pressed={consumeEnabled}
      >
        {updateTenant.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : null}
        {consumeEnabled ? "Enabled" : "Disabled"}
      </AdminWriteButton>
    </div>
  );
}
