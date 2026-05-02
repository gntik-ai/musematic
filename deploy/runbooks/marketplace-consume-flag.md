# Marketplace `consume_public_marketplace` Flag Runbook

UPD-049 added a per-Enterprise-tenant feature flag that lets an Enterprise
tenant consume the public marketplace (default-tenant–scoped agents) in
read-only fashion. This runbook covers the toggle procedure, the audit
trail, and revocation.

## Pre-flight checks

Before flipping the flag, confirm:

1. The tenant is an **Enterprise** tenant. The flag is meaningless on the
   default tenant — the service refuses with HTTP 422
   (`feature_flag_invalid_for_tenant_kind`) if attempted.
2. A signed contract addendum is in place authorising public-marketplace
   consumption. The audit-chain entry created by the toggle is the durable
   record on our side; keep the contract in the legal repository as the
   complementary record.
3. The tenant's primary technical contact has been notified that the
   flag is about to flip.

## Enable the flag

Use a super-admin JWT.

```bash
TENANT_ID=...                # the Enterprise tenant's UUID
TENANT_SLUG=acme

curl -X PATCH "$API/api/v1/admin/tenants/$TENANT_ID" \
  -H "Authorization: Bearer $SUPER_ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{ "feature_flags": { "consume_public_marketplace": true } }'
```

Expected: HTTP 200 with `feature_flags.consume_public_marketplace: true`
in the response body.

### Verify the side effects

```bash
# Audit chain entry
psql "$DATABASE_URL" -c "
  SELECT event_type, payload->>'flag_name' AS flag, payload->>'to_value' AS value
    FROM audit_chain_entries
   WHERE tenant_id = '$TENANT_ID'
     AND event_type = 'tenants.feature_flag_changed'
   ORDER BY entry_seq DESC
   LIMIT 1;
"
# expected: tenants.feature_flag_changed | consume_public_marketplace | true

# Kafka envelope
kafkactl consume tenants.lifecycle --max-messages=5 --from-beginning=false \
  | grep -E '(feature_flag_changed|consume_public_marketplace)'
# expected: an envelope with event_type='tenants.feature_flag_changed' and
# the from/to_value pair

# Resolver cache invalidation
# A request from the tenant should now report consume_public_marketplace=true.
# If the resolver still reports false, restart the tenant's pod or wait for
# the cache TTL — the invalidation is best-effort, not synchronous.
```

## Tell the tenant

Send the tenant's primary contact a notification with the following template:

> Subject: Public marketplace access enabled for {{tenant_slug}}
>
> The public marketplace is now available read-only to {{tenant_slug}}
> users. Public-scope agents will appear in marketplace search alongside
> your tenant's private agents and are clearly labelled "From public
> marketplace". Cost attribution for any public-agent execution flows to
> {{tenant_slug}}'s billing scope.
>
> If you want to fork a public agent into your tenant for private edits,
> use the "Fork to my tenant" button on the agent's detail page.
>
> Per UPD-049, your data does not leak the other way — public-marketplace
> agents have no visibility into {{tenant_slug}}'s private agents or data.

## Revoke the flag

```bash
curl -X PATCH "$API/api/v1/admin/tenants/$TENANT_ID" \
  -H "Authorization: Bearer $SUPER_ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{ "feature_flags": { "consume_public_marketplace": false } }'
```

After revocation:

- Public agents disappear from the tenant's marketplace search results.
- Existing forks remain in the tenant — forks are private copies; the
  consume flag only governs visibility of the **upstream** public listings.
- Source-update notifications stop arriving for fork owners (the
  `MarketplaceFanoutConsumer` only fans out to forks whose owners can
  read the source agent — without the consume flag, the source becomes
  invisible again to the tenant's users).

## Failure modes

| Symptom | Cause | Recovery |
|---|---|---|
| HTTP 422 `feature_flag_invalid_for_tenant_kind` | Tenant is the default tenant | Don't run this on the default tenant. The default tenant is the publisher of the public marketplace, not a consumer. |
| HTTP 422 `feature_flag_not_in_allowlist` | Misspelled flag name | Use exactly `consume_public_marketplace`. Other flags require their own service-layer plumbing. |
| HTTP 404 `tenant_not_found` | Wrong tenant UUID | Look up the tenant via `/api/v1/admin/tenants?q=<slug>`. |
| HTTP 200 but consumers still don't see public agents | Resolver cache stale | The cache invalidation runs on the same Redis pub/sub channel as tenant updates; wait up to 60 s or restart the tenant's pod. If the issue persists, run the `tenant-cache-invalidate` operation runbook. |

## Constitutional guard

Public publishing remains restricted to the default tenant under the
three-layer Enterprise refusal (UI scope-picker disabled state +
service-layer `PublicScopeNotAllowedForEnterpriseError` + database CHECK
constraint `registry_agent_profiles_public_only_default_tenant`). The
consume flag does NOT relax that — Enterprise tenants are pure consumers
of the public hub, never publishers to it.
