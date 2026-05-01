"use client";

import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2, Loader2, Upload } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { AdminWriteButton } from "@/components/features/admin/AdminWriteButton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import {
  useDpaUpload,
  useProvisionTenant,
  type TenantProvisionPayload,
  type TenantRegion,
} from "@/lib/hooks/use-admin-tenants";
import { toast } from "@/lib/hooks/use-toast";

export const TENANT_RESERVED_SLUGS = [
  "api",
  "grafana",
  "status",
  "www",
  "admin",
  "platform",
  "webhooks",
  "public",
  "docs",
  "help",
] as const;

const TENANT_REGION_VALUES = ["global", "eu-central", "us-east", "us-west"] as const;
const TENANT_SLUG_PATTERN = /^[a-z][a-z0-9-]{0,30}[a-z0-9]$/;

const optionalUrl = z.union([z.string().trim().url(), z.literal("")]).optional();
const optionalText = z.string().trim().optional();
const accentColor = z
  .union([z.string().trim().regex(/^#[0-9a-fA-F]{6}$/), z.literal("")])
  .optional();

const dpaFileSchema = z
  .custom<File>(
    (value): value is File =>
      typeof File !== "undefined" && value instanceof File && value.size > 0,
    "DPA PDF is required",
  )
  .refine(
    (file) => file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf"),
    "DPA must be a PDF",
  );

const tenantProvisionSchema = z.object({
  slug: z
    .string()
    .trim()
    .min(2, "Slug must be at least 2 characters")
    .max(32, "Slug must be 32 characters or less")
    .regex(TENANT_SLUG_PATTERN, "Use lowercase letters, numbers, and hyphens")
    .refine(
      (slug) => !TENANT_RESERVED_SLUGS.includes(slug as (typeof TENANT_RESERVED_SLUGS)[number]),
      "This slug is reserved",
    ),
  display_name: z.string().trim().min(1, "Display name is required").max(128),
  region: z.enum(TENANT_REGION_VALUES),
  first_admin_email: z.string().trim().email("Valid email required"),
  dpa_version: z.string().trim().min(1, "DPA version is required").max(32),
  dpaFile: dpaFileSchema,
  contract_number: optionalText,
  signed_at: optionalText,
  signed_by: optionalText,
  logo_url: optionalUrl,
  accent_color_hex: accentColor,
});

type TenantProvisionFormValues = z.infer<typeof tenantProvisionSchema>;

function nonEmpty(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

function buildPayload(
  values: TenantProvisionFormValues,
  dpaArtifactId: string,
): TenantProvisionPayload {
  const contractMetadata: Record<string, unknown> = {};
  const contractNumber = nonEmpty(values.contract_number);
  const signedAt = nonEmpty(values.signed_at);
  const signedBy = nonEmpty(values.signed_by);
  if (contractNumber) {
    contractMetadata.contract_number = contractNumber;
  }
  if (signedAt) {
    contractMetadata.signed_at = signedAt;
  }
  if (signedBy) {
    contractMetadata.signed_by = signedBy;
  }

  const brandingConfig: TenantProvisionPayload["branding_config"] = {};
  const logoUrl = nonEmpty(values.logo_url);
  const accentColorHex = nonEmpty(values.accent_color_hex);
  if (logoUrl) {
    brandingConfig.logo_url = logoUrl;
  }
  if (accentColorHex) {
    brandingConfig.accent_color_hex = accentColorHex;
  }

  return {
    slug: values.slug,
    display_name: values.display_name,
    region: values.region as TenantRegion,
    first_admin_email: values.first_admin_email,
    dpa_artifact_id: dpaArtifactId,
    dpa_version: values.dpa_version,
    contract_metadata: contractMetadata,
    branding_config: brandingConfig,
  };
}

function errorMessage(error: unknown): string | null {
  if (!error) {
    return null;
  }
  return error instanceof Error ? error.message : "Tenant provisioning failed";
}

export function TenantProvisionForm() {
  const router = useRouter();
  const dpaUpload = useDpaUpload();
  const provisionTenant = useProvisionTenant();
  const form = useForm<TenantProvisionFormValues>({
    resolver: zodResolver(tenantProvisionSchema),
    defaultValues: {
      slug: "",
      display_name: "",
      region: "eu-central",
      first_admin_email: "",
      dpa_version: "v1",
      contract_number: "",
      signed_at: "",
      signed_by: "",
      logo_url: "",
      accent_color_hex: "",
    },
  });
  const pending = dpaUpload.isPending || provisionTenant.isPending;
  const combinedError = errorMessage(dpaUpload.error ?? provisionTenant.error);

  const submit = form.handleSubmit(async (values) => {
    const upload = await dpaUpload.mutateAsync(values.dpaFile);
    const provisioned = await provisionTenant.mutateAsync(
      buildPayload(values, upload.dpa_artifact_id),
    );
    toast({
      title: "Tenant provisioned",
      description: `${provisioned.slug} is ready for first-admin setup.`,
      variant: "success",
    });
    router.push(`/admin/tenants/${provisioned.id}`);
  });

  return (
    <Form {...form}>
      <form className="space-y-5" onSubmit={submit}>
        {combinedError ? (
          <Alert variant="destructive">
            <AlertTitle>Provisioning failed</AlertTitle>
            <AlertDescription>{combinedError}</AlertDescription>
          </Alert>
        ) : null}

        <div className="grid gap-5 rounded-md border bg-card p-5 lg:grid-cols-2">
          <FormField
            control={form.control}
            name="slug"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Slug</FormLabel>
                <FormControl>
                  <Input autoComplete="off" placeholder="acme" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="display_name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Display name</FormLabel>
                <FormControl>
                  <Input autoComplete="organization" placeholder="Acme Corp" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="region"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Region</FormLabel>
                <FormControl>
                  <Select {...field}>
                    {TENANT_REGION_VALUES.map((region) => (
                      <option key={region} value={region}>
                        {region}
                      </option>
                    ))}
                  </Select>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="first_admin_email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>First admin email</FormLabel>
                <FormControl>
                  <Input autoComplete="email" placeholder="cto@acme.com" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <div className="grid gap-5 rounded-md border bg-card p-5 lg:grid-cols-2">
          <FormField
            control={form.control}
            name="dpaFile"
            render={({ field }) => (
              <FormItem>
                <FormLabel>DPA PDF</FormLabel>
                <FormControl>
                  <Input
                    accept="application/pdf,.pdf"
                    type="file"
                    onBlur={field.onBlur}
                    onChange={(event) => field.onChange(event.target.files?.[0])}
                    ref={field.ref}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="dpa_version"
            render={({ field }) => (
              <FormItem>
                <FormLabel>DPA version</FormLabel>
                <FormControl>
                  <Input placeholder="v3-2026-01" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="contract_number"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Contract number</FormLabel>
                <FormControl>
                  <Input placeholder="ACME-2026-001" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="signed_at"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Signed date</FormLabel>
                <FormControl>
                  <Input placeholder="2026-04-30" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="signed_by"
            render={({ field }) => (
              <FormItem className="lg:col-span-2">
                <FormLabel>Signed by</FormLabel>
                <FormControl>
                  <Input placeholder="Alice CTO" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <div className="grid gap-5 rounded-md border bg-card p-5 lg:grid-cols-2">
          <FormField
            control={form.control}
            name="logo_url"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Logo URL</FormLabel>
                <FormControl>
                  <Input placeholder="https://static.acme.com/logo.svg" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="accent_color_hex"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Accent color</FormLabel>
                <FormControl>
                  <div className="flex gap-2">
                    <Input placeholder="#0078d4" {...field} />
                    <input
                      aria-label="Accent color picker"
                      className="h-10 w-12 rounded-md border bg-background"
                      type="color"
                      value={field.value || "#0078d4"}
                      onChange={(event) => field.onChange(event.target.value)}
                    />
                  </div>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2">
          {dpaUpload.isSuccess && !provisionTenant.isSuccess ? (
            <span className="inline-flex items-center gap-2 text-sm text-muted-foreground">
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              DPA uploaded
            </span>
          ) : null}
          <AdminWriteButton disabled={pending} disabledByMaintenance type="submit">
            {pending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Provisioning
              </>
            ) : (
              <>
                <Upload className="h-4 w-4" />
                Provision tenant
              </>
            )}
          </AdminWriteButton>
        </div>
      </form>
    </Form>
  );
}
