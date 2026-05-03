# Abuse prevention (UPD-050)

This guide walks platform-staff operators through the abuse-prevention layer that protects the public default tenant from bot signups, free-tier cost mining, credential stuffing, and disposable-email churn.

The feature ships seven defensive capabilities, each independently toggleable:

1. **Velocity rules** per IP, ASN (Autonomous System Number), and email domain.
2. **Disposable-email detection** against a curated, weekly-refreshed blocklist.
3. **Account-suspension automation** when abuse patterns trigger.
4. **CAPTCHA on signup** (Turnstile or hCaptcha; off by default).
5. **Geo-blocking** (off by default; super admin can enable per-country denial).
6. **Fraud-scoring integration** (off by default; pluggable adapter for MaxMind minFraud or Sift).
7. **Free-tier runtime cost protection** that surfaces plan-defined caps on model tier, execution time, and reasoning depth.

A super-admin admin surface at `/admin/security/*` lets operators tune thresholds, review suspensions, and override per-domain blocks.

## Threshold tuning

Navigate to `/admin/security/abuse-prevention`. Each setting from `abuse_prevention_settings` is rendered with an inline editor. Changes take effect within 30 seconds and are recorded in the audit chain.

Default safe configuration:

| Setting | Default | Notes |
|---------|---------|-------|
| `velocity_per_ip_hour` | 5 | Refusal threshold per IP per rolling hour. |
| `velocity_per_asn_hour` | 50 | Per ASN per rolling hour. |
| `velocity_per_email_domain_day` | 20 | Per email domain per rolling day. |
| `captcha_enabled` | false | Enable when you observe a sustained attack. |
| `captcha_provider` | "turnstile" | "turnstile" / "hcaptcha" / "disabled". |
| `geo_block_mode` | "disabled" | "disabled" / "deny_list" / "allow_list". |
| `disposable_email_blocking` | true | Always-on by default. |
| `fraud_scoring_provider` | "disabled" | Operators register a provider explicitly. |

Allowlisting trusted enterprise NATs prevents legitimate office traffic from tripping per-IP velocity. Edit at `/admin/security/abuse-prevention` (allowlist section) — entries can be IP CIDR ranges or email domains.

## Suspension queue

`/admin/security/suspensions` lists active suspensions with the reason code, evidence summary, applied-at timestamp, and source (system / super_admin / tenant_admin). System-applied suspensions are styled distinctly from human-applied ones so the operator can prioritise.

Lift a false positive by clicking through to the suspension's detail page and supplying a reason. The user is notified via the UPD-042 inbox; the lift is audit-chained.

**Privileged-role exemption**: auto-suspension never applies to platform-staff or tenant-admin roles. Manual super-admin action remains the only path to suspend a privileged user.

## Disposable-email overrides

`/admin/security/email-overrides` lets the super admin add per-domain `allow` (un-block) or `block` (force-block) overrides. Overrides take precedence over the upstream blocklist.

The upstream list (from `disposable-email-domains/disposable-email-domains` GitHub) is refreshed weekly by a cron job; click "Refresh blocklist now" to trigger a manual sync.

**Resolution order** (per request):
1. Super-admin override `allow` for the domain → allow.
2. Super-admin override `block` for the domain → block.
3. Domain in upstream blocklist → block.
4. Otherwise → allow.

## Geo-block configuration

`/admin/security/geo-policy` exposes the geo-block knob. Modes are mutually exclusive:

- `disabled` (default) — geo-block off entirely.
- `deny_list` — block listed countries; allow all others.
- `allow_list` — allow only listed countries; block all others.

Switching mode requires explicit confirmation (the UI surfaces a checkbox) so an operator does not accidentally inherit a deny-list when intending an allow-list.

If the GeoLite2 database is missing (red badge on the page), geo-block degrades gracefully — country resolution returns null and no rules fire. Re-run `helm upgrade --reuse-values` to retrigger the GeoLite2 download Job.

## Free-tier cost protection

The Free plan defines four runtime caps:

- `allowed_model_tier='cheap_only'` — refuses premium-model invocations at the model-router layer.
- `monthly_execution_cap=100` — refuses new executions after the 100th in a calendar month.
- `max_execution_time_seconds=300` — auto-terminates executions running past 5 minutes.
- `max_reasoning_depth=5` — refuses reasoning past depth 5.

Cap-fired events are observable on the abuse-prevention dashboard and queryable via the per-workspace cost-protection panel.

## Operator runbooks

### Velocity guard refuses every signup

Redis is unreachable. The guard fails closed (refusing is safer than admitting an unbounded burst). Check `redis-cli ping`. Until Redis recovers, signups are blocked.

### Disposable-email check returns false positives

A legitimate domain is on the upstream blocklist. Add an `allow` override at `/admin/security/email-overrides`. The override takes effect on the next signup.

### Auto-suspension fires against a privileged user

This is a bug — should not happen by design (FR-744.3). The suspension service refuses to write the row in the first place. If you see one, file an incident and manually delete the orphaned row from `account_suspensions`.

### Fraud-scoring upstream is degraded

Signups still complete (FR-747.1 graceful-degradation requirement). The structured-log surface shows a WARN line. Latency budget: ≤1 second p95 above the no-fraud-scoring baseline.
