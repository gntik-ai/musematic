# Roadmap

Features with a `spec.md` in the repo but not yet implemented (or only
partially implemented) land here. This page is distinct from
[Features](features/index.md) which catalogues implemented or
in-progress specs.

!!! warning "This list is based on the current `main` branch"
    Anything in the `main` branch today is considered in-progress or
    done — see the [Features catalogue](features/index.md). The
    roadmap below captures what is explicitly planned but not yet on
    `main`.

## Audit-pass (constitution v1.2.0)

The constitution's v1.2.0 amendment introduces 13 new features
(UPD-023 through UPD-035). None of these have spec folders on `main`
yet — they are announced in the constitution as the next major pass.

| Working name | Summary |
|---|---|
| UPD-023: Privacy compliance | DSR, RTBF cascade, DLP, PIA, regional residency. |
| UPD-024: Security compliance | SBOM, vuln scanning, pentest tracking, secret rotation, JIT credentials, hash-chain audit, compliance evidence. |
| UPD-025: Multi-region ops | Region as first-class dimension, replication monitoring, failover, maintenance mode. |
| UPD-026: Model catalog | Approved models registry, model cards, fallback policies, provider credentials. |
| UPD-027: Cost governance | Attribution, chargeback, budgets, forecasting. |
| UPD-028: Multi-channel notifications | 6 channels (Slack, Teams, email, SMS, webhook, in-app). |
| UPD-029: API governance | OpenAPI generation, SDKs, per-principal rate limiting. |
| UPD-030: Localisation | Locale files, i18n workflow, user locale preferences, 6 languages. |
| UPD-031: Incident response | Incidents, runbooks, post-mortems. |
| UPD-032: Content safety & fairness | Content moderation + fairness scorer. |
| UPD-033: Tags, labels, saved views | Polymorphic tagging + saved filter combinations. |
| UPD-034: Log aggregation + dashboards | Loki + Promtail + 14 new Grafana dashboards. |
| UPD-035: Capstone | Unified observability Helm bundle + 7 new E2E journeys. |

See the constitution at
[`.specify/memory/constitution.md`](https://github.com/gntik-ai/musematic/blob/main/.specify/memory/constitution.md)
for the full detail.

## Observed gaps (from the current main branch)

These are real gaps noted during docs generation that should land in
incremental work, not only in the audit-pass:

### Admin UI path

No dedicated `/admin/*` URL path — admin actions are only exposed via
REST endpoints guarded by `platform_admin` / `superadmin` roles. Adding
a dedicated UI surface would make admin workflows (signup mode
switching, role assignment, lockout clearing) easier.

### OAuth provider configuration at runtime

[Spec 058][s058] (OAuth2 social login) exists but the admin API for
configuring Google / GitHub OAuth providers is not yet present in
`apps/control-plane/src/platform/auth/`. Journey tests use mocks
(`services/mock-google-oidc/`, `services/mock-github-oauth/`).

### Per-user and per-workspace quotas

`User.max_workspaces` is enforced, but there is no admin PATCH
endpoint to change it. Per-workspace resource caps (agent count,
execution count, storage bytes) are not yet wired on the
`Workspace.settings` model.

### Canonical `docker-compose.yml` for local-dev

The repo ships per-feature docker-compose files under
`apps/control-plane/tests/` but no top-level canonical one for
developers.

### Consolidated metric catalogue

Each bounded context emits its own metrics; the list is not
consolidated in a single catalogue. Ties into
[Administration › Observability](administration/observability.md).

### HashiCorp Vault adapter

`VAULT_MODE=vault` is declared but the adapter raises
`NotImplementedError`. Mock-mode vault works.

### Consolidated troubleshooting

Per-feature `quickstart.md` notes exist but no cross-cutting
troubleshooting guide. Partial coverage lives in [FAQ](faq.md).

## Fully planned / unplanned specs on main

TODO(andrea): walk the `Status:` headers of every `specs/*/spec.md`
file and list the ones marked `Planned` (vs. `Draft` / `In Progress`).
The auto-generated [features catalogue](features/index.md) surfaces
the current status per feature.

[s058]: https://github.com/gntik-ai/musematic/tree/main/specs/058-oauth2-social-login
