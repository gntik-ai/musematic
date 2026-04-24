# Security Compliance and Supply Chain

Feature 074 adds a security-compliance bounded context to the control plane. It covers supply-chain artefacts, vulnerability gating, zero-downtime secret rotation, JIT credentials, pentest tracking, compliance evidence, and a cryptographic audit chain.

## Runtime Capabilities

- **Audit chain**: `/api/v1/security/audit-chain/*` verifies append-only audit integrity, exports signed attestations, and exposes the Ed25519 public key for external verification.
- **SBOM ingest**: release publishers upload SPDX and CycloneDX SBOMs to `/api/v1/security/sbom`; the service computes and stores deterministic SHA-256 hashes and writes audit-chain evidence.
- **Vulnerability gating**: CI scanner output is normalized by `ci/normalize_scan_results.py`, uploaded to `/api/v1/security/scans/{release_version}/results`, and blocked when non-excepted findings meet scanner severity thresholds.
- **Secret rotation**: `/api/v1/security/rotations` manages schedules and emergency triggers with overlap windows. Scheduler workers trigger due rotations and expire overlap windows without exposing secret values.
- **JIT credentials**: `/api/v1/security/jit-grants` supports request, peer approval, usage audit, and revocation. Revoked JIT JWTs are denied by middleware through `jit:revoked:{jti}` Redis lookups.
- **Pentest tracking**: `/api/v1/security/pentests` schedules tests, imports findings, computes SLA due dates, scans overdue items, and exports history.
- **Compliance evidence**: security events are consumed into framework-control evidence rows. Manual evidence uploads are stored under the configured compliance evidence bucket and bundle exports are signed.

## CI Integration

The CI workflow now runs the security scanner matrix for Python, Go, Node, and built images. Scanner output is uploaded as artifacts, normalized, and optionally posted to the platform when `PLATFORM_API_URL` and a release-publisher token or OIDC exchange are configured.

The release workflow generates both CycloneDX and SPDX SBOMs for each image, canonicalizes them with `ci/normalize_sbom.py`, uploads them as release assets, and posts them to the platform when release-publisher credentials are configured.

## Operational Notes

- Security-compliance workers are registered for `worker` and `scheduler` profiles.
- The compliance-evidence consumer subscribes to all security topics plus `security.audit.chain.verified`.
- Audit-chain hooks are wired into OAuth, A2A gateway, registry lifecycle audit, and MCP invocation audit paths.
- Migration `058_security_compliance.py` creates the tables, seed controls, JIT and pentest policies, and append-only audit trigger.
