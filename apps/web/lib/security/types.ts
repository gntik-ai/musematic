/**
 * UPD-050 — TypeScript mirrors of the Pydantic schemas in
 * `apps/control-plane/src/platform/security_abuse/schemas.py`. Hand-rolled
 * to keep the change cost low; once UPD-050 ships, the OpenAPI generator
 * (UPD-073 API governance) supersedes this file.
 */

export type SuspensionReason =
  | "velocity_repeat"
  | "fraud_score"
  | "cost_burn_rate"
  | "disposable_email_pattern"
  | "captcha_replay"
  | "geo_violation"
  | "manual"
  | "tenant_admin";

export type SuspendedBy = "system" | "super_admin" | "tenant_admin";

export interface SuspensionView {
  id: string;
  user_id: string;
  tenant_id: string;
  reason: SuspensionReason;
  suspended_at: string;
  suspended_by: SuspendedBy;
  suspended_by_user_id: string | null;
  lifted_at: string | null;
  lifted_by_user_id: string | null;
}

export interface SuspensionDetailView extends SuspensionView {
  evidence_json: Record<string, unknown>;
  lift_reason: string | null;
}

export interface SuspensionLiftRequest {
  reason: string;
}

export interface SuspensionCreateRequest {
  user_id: string;
  reason: SuspensionReason;
  evidence?: Record<string, unknown>;
  notes?: string | null;
}

export interface EmailOverride {
  domain: string;
  created_at: string;
  created_by_user_id: string;
  reason: string | null;
}

export interface EmailOverrideAdd {
  domain: string;
  reason?: string | null;
}

export type TrustedAllowlistKind = "ip" | "asn";

export interface TrustedAllowlistEntry {
  id: string;
  kind: TrustedAllowlistKind;
  value: string;
  created_at: string;
  reason: string | null;
}

export interface TrustedAllowlistAdd {
  kind: TrustedAllowlistKind;
  value: string;
  reason?: string | null;
}

export type GeoBlockMode = "disabled" | "deny" | "allow_only";

export interface GeoPolicyView {
  mode: GeoBlockMode;
  country_codes: string[];
}

export interface GeoPolicyUpdate {
  mode: GeoBlockMode;
  country_codes: string[];
}

/** Map of arbitrary setting key → value. The values are loosely typed
 *  because the JSONB shape varies per setting. */
export type AbusePreventionSettings = Record<string, unknown>;
