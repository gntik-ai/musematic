# Quickstart & Test Scenarios: IBOR Integration and Agent Decommissioning

**Feature**: `specs/056-ibor-agent-decommissioning/spec.md`
**Date**: 2026-04-18

---

## Setup Prerequisites

```python
WORKSPACE_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
AGENT_FQN    = "acme/finance/tax-reconciler"
ADMIN_USER   = UUID("11111111-1111-1111-1111-111111111111")
MEMBER_USER  = UUID("22222222-2222-2222-2222-222222222222")
```

---

## US1 — IBOR Pull Sync

### Scenario 1 — Pull sync imports user-role mapping

```python
connector = await service.create_connector(IBORConnectorCreate(
    name="test-oidc", source_type=IBORSourceType.oidc, sync_mode=IBORSyncMode.pull,
    cadence_seconds=3600, credential_ref="test-oidc-creds",
    role_mapping_policy=[IBORRoleMappingRule(
        directory_group="Platform-Admins", platform_role="platform_admin"
    )],
), actor_id=ADMIN_USER)

# Mock OIDC returns alice@corp.com in Platform-Admins group
result = await sync_service.run_sync(connector.id, triggered_by=ADMIN_USER)

assert result.status == IBORSyncRunStatus.succeeded
assert result.counts["roles_added"] == 1
user_roles = await repo.list_user_roles(user_email="alice@corp.com")
assert "platform_admin" in [r.role for r in user_roles]
assert user_roles[0].source_connector_id == connector.id
```

### Scenario 2 — Role revoked when user removed from directory group

```python
# Alice has platform_admin from connector; mock OIDC now omits her from Platform-Admins
result = await sync_service.run_sync(connector.id, triggered_by=ADMIN_USER)

assert result.counts["roles_revoked"] == 1
user_roles = await repo.list_user_roles(user_email="alice@corp.com")
assert not any(r.role == "platform_admin" and r.source_connector_id == connector.id
               for r in user_roles)
```

### Scenario 3 — Manual assignment preserved during IBOR sync (FR-003)

```python
# Admin manually grants platform_admin to bob@corp.com (source_connector_id=NULL)
await rbac.grant_role(bob_id, "platform_admin", workspace_id=None, source_connector_id=None)
# Bob is NOT in any directory group
result = await sync_service.run_sync(connector.id, triggered_by=ADMIN_USER)
# Bob's manual role is preserved
bob_roles = await repo.list_user_roles(user_id=bob_id)
assert any(r.role == "platform_admin" and r.source_connector_id is None for r in bob_roles)
```

### Scenario 4 — Partial success on per-user failure

```python
# Mock OIDC returns [alice: valid, missing@corp.com: not in platform]
result = await sync_service.run_sync(connector.id, triggered_by=ADMIN_USER)
assert result.status == IBORSyncRunStatus.partial_success
assert result.counts["errors"] == 1
assert any(err["email"] == "missing@corp.com" for err in result.error_details)
# Alice still synced successfully
assert result.counts["roles_added"] >= 1
```

### Scenario 5 — Concurrent sync trigger rejected via Redis lock

```python
# Start run #1 (runs for 5 seconds in mock)
task1 = asyncio.create_task(sync_service.run_sync(connector.id, ADMIN_USER))
await asyncio.sleep(0.1)  # let #1 acquire lock

# Run #2 attempts in parallel
with pytest.raises(SyncInProgressError):
    await sync_service.run_sync(connector.id, ADMIN_USER)
await task1
```

---

## US2 — IBOR Push Sync

### Scenario 6 — Push sync exports active agents to SCIM endpoint

```python
push_connector = await service.create_connector(IBORConnectorCreate(
    name="corp-scim", source_type=IBORSourceType.scim, sync_mode=IBORSyncMode.push,
    cadence_seconds=86400, credential_ref="scim-creds", role_mapping_policy=[],
), actor_id=ADMIN_USER)

result = await sync_service.run_sync(push_connector.id, triggered_by=ADMIN_USER)

# Mock SCIM endpoint should have received 3 active agents (those with status in
# {published, disabled, deprecated})
assert mock_scim.post_user.call_count == 3
assert result.status == IBORSyncRunStatus.succeeded
```

### Scenario 7 — Decommissioned agent pushed as inactive

```python
await agent_service.decommission_agent(WORKSPACE_ID, agent_id, reason="EOL", actor_id=ADMIN_USER, runtime_controller=mock_rc)
result = await sync_service.run_sync(push_connector.id, triggered_by=ADMIN_USER)
scim_call = next(c for c in mock_scim.post_user.calls if c.fqn == AGENT_FQN)
assert scim_call.active is False
```

---

## US3 — Decommissioning

### Scenario 8 — Decommission with reason stops instances and sets terminal state

```python
mock_rc.list_active_instances.return_value = ["inst-1", "inst-2"]
response = await agent_service.decommission_agent(
    WORKSPACE_ID, agent_id, reason="Regulatory retirement Q2 2026",
    actor_id=ADMIN_USER, runtime_controller=mock_rc,
)
assert response.active_instances_stopped == 2
assert mock_rc.stop_runtime.call_count == 2

profile = await repo.get_profile(agent_id)
assert profile.status is LifecycleStatus.decommissioned
assert profile.decommissioned_at is not None
assert profile.decommission_reason == "Regulatory retirement Q2 2026"
assert profile.decommissioned_by == ADMIN_USER
```

### Scenario 9 — Decommission without required role → 403

```python
with pytest.raises(ForbiddenError):
    await agent_service.decommission_agent(
        WORKSPACE_ID, agent_id, reason="test reason ten chars",
        actor_id=MEMBER_USER, runtime_controller=mock_rc,
    )
```

### Scenario 10 — Decommission with short reason → 422

```python
response = await http_client.post(
    f"/api/v1/registry/{WORKSPACE_ID}/agents/{agent_id}/decommission",
    json={"reason": "too short"},  # 9 chars
    headers=admin_auth,
)
assert response.status_code == 422
```

### Scenario 11 — Decommission is idempotent

```python
r1 = await agent_service.decommission_agent(WORKSPACE_ID, agent_id, reason="first", actor_id=ADMIN_USER, runtime_controller=mock_rc)
r2 = await agent_service.decommission_agent(WORKSPACE_ID, agent_id, reason="second", actor_id=ADMIN_USER, runtime_controller=mock_rc)
assert r1.decommissioned_at == r2.decommissioned_at
assert r1.decommission_reason == r2.decommission_reason == "first"
```

### Scenario 12 — Decommission emits Kafka event

```python
await agent_service.decommission_agent(WORKSPACE_ID, agent_id, reason="EOL", actor_id=ADMIN_USER, runtime_controller=mock_rc)
mock_producer.publish.assert_called()
event = mock_producer.publish.call_args[0][0]
assert event["event_type"] == "agent_decommissioned"
assert event["data"]["fqn"] == AGENT_FQN
assert event["data"]["active_instance_count_at_decommission"] == 2
```

---

## US4 — Irreversibility

### Scenario 13 — State transition from decommissioned → published rejected

```python
await decommission_agent(agent_id)
with pytest.raises(InvalidTransitionError):
    await agent_service.transition_lifecycle(
        WORKSPACE_ID, agent_id,
        LifecycleTransitionRequest(target_status=LifecycleStatus.published),
        actor_id=ADMIN_USER,
    )
```

### Scenario 14 — FQN reuse creates new record with new id

```python
old = await create_agent(fqn=AGENT_FQN)
await decommission_agent(old.id)
new = await registry_service.register_agent(... same fqn ...)
assert new.id != old.id
old_after = await repo.get_profile(old.id)
assert old_after.status is LifecycleStatus.decommissioned
assert old_after.decommissioned_at is not None
```

### Scenario 15 — decommissioned_at/reason cannot be cleared

```python
await decommission_agent(agent_id, reason="first")
profile = await repo.get_profile(agent_id)
# Attempt direct field clear via repo update
with pytest.raises(IntegrityError | DecommissionImmutableError):
    await repo.update_profile(agent_id, decommissioned_at=None, decommission_reason=None)
```

---

## US5 — Cross-surface invisibility

### Scenario 16 — Decommissioned agent excluded from marketplace search

```python
await decommission_agent(agent_id)
await asyncio.sleep(0.5)  # await index refresh
results = await marketplace.search(query="tax")
assert agent_id not in [a.id for a in results]
```

### Scenario 17 — Direct FQN lookup returns decommissioned state, no invocation

```python
await decommission_agent(agent_id)
response = await http_client.get(f"/api/v1/marketplace/agents/acme/finance/tax-reconciler")
assert response.status_code == 200
body = response.json()
assert body["status"] == "decommissioned"
assert body["invocable"] is False
```

### Scenario 18 — Workflow-builder agent picker excludes decommissioned

```python
await decommission_agent(agent_id)
picker = await workflow_service.list_agents_for_picker(WORKSPACE_ID, ADMIN_USER)
assert agent_id not in [a.id for a in picker]
```

### Scenario 19 — Audit/analytics queries still return decommissioned agent

```python
await decommission_agent(agent_id)
# Prior executions still resolve
audit = await analytics.agent_execution_summary(agent_id)
assert audit is not None
assert audit.total_executions > 0  # prior data preserved
```

---

## Migration

### Scenario 20 — Alembic 044 applies and rolls back

```python
run_migrations_up_to("044_ibor_and_decommission")
assert table_exists("ibor_connectors")
assert table_exists("ibor_sync_runs")
assert column_exists("registry_agent_profiles", "decommissioned_at")
assert column_exists("registry_agent_profiles", "decommission_reason")
assert column_exists("registry_agent_profiles", "decommissioned_by")
assert column_exists("user_roles", "source_connector_id")
# 'decommissioned' enum value exists
assert "decommissioned" in enum_values("registry_lifecycle_status")

run_migrations_down_to("043_runtime_warm_pool_targets")
assert not table_exists("ibor_connectors")
assert not column_exists("registry_agent_profiles", "decommissioned_at")
# Note: enum value 'decommissioned' remains after downgrade (PostgreSQL limitation)
```

### Scenario 21 — FR-019/FR-020 backward compatibility

```python
# With no connectors configured and no decommissioned agents
await sync_service.run_scheduled_syncs()  # no-op; no runs executed
marketplace_results = await marketplace.search(query="")
# Existing test fixtures return identical counts to pre-feature baseline
assert len(marketplace_results) == baseline_count
```
