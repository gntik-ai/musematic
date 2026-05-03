"use client";

/**
 * UPD-050 T031 — Abuse-prevention overview + tuning page.
 *
 * Lists all abuse_prevention_settings rows with per-knob inline
 * editors. Powers the super-admin tuning surface from
 * `quickstart.md` Walkthrough 1.
 */

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ThresholdEditor,
  ThresholdEditorSkeleton,
} from "@/components/features/admin-security/threshold-editor";
import { useAbusePreventionSettings } from "@/lib/hooks/use-abuse-prevention-settings";

const SETTING_DESCRIPTIONS: Record<string, string> = {
  velocity_per_ip_hour: "Rolling-hour signup attempts allowed per source IP.",
  velocity_per_asn_hour: "Rolling-hour signup attempts allowed per source ASN.",
  velocity_per_email_domain_day:
    "Rolling-day signup attempts allowed per email domain.",
  captcha_enabled: "Whether CAPTCHA challenges show on the signup form.",
  captcha_provider: "CAPTCHA provider — turnstile / hcaptcha / disabled.",
  geo_block_mode:
    "Geo-block mode — disabled / deny_list / allow_list (mutually exclusive).",
  geo_block_country_codes:
    "ISO-3166-1 alpha-2 codes; meaning depends on geo_block_mode.",
  fraud_scoring_provider:
    "Fraud-scoring provider — disabled / minfraud / sift.",
  disposable_email_blocking:
    "Whether the disposable-email blocklist is consulted at signup.",
  auto_suspension_repeated_velocity_window_hours:
    "Lookback window for repeated-velocity auto-suspension.",
  auto_suspension_repeated_velocity_min_hits:
    "Minimum velocity hits in window for auto-suspension.",
  auto_suspension_cost_burn_rate_threshold_usd_per_hour:
    "USD-per-hour cost burn rate that triggers auto-suspension.",
};

export default function AbusePreventionPage() {
  const settingsQuery = useAbusePreventionSettings();

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-normal">
          Abuse prevention
        </h1>
        <p className="text-sm text-muted-foreground">
          Tune the signup-side and runtime defensive layers. Changes take
          effect within 30 seconds and are recorded in the audit chain.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Settings</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {settingsQuery.isLoading ? (
            <>
              <ThresholdEditorSkeleton />
              <ThresholdEditorSkeleton />
              <ThresholdEditorSkeleton />
            </>
          ) : settingsQuery.isError ? (
            <p className="col-span-full rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
              Could not load settings.
            </p>
          ) : (
            settingsQuery.data?.settings.map((s) => (
              <ThresholdEditor
                key={s.key}
                settingKey={s.key}
                currentValue={s.value}
                description={SETTING_DESCRIPTIONS[s.key]}
              />
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
