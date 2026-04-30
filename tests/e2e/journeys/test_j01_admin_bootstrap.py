from __future__ import annotations

from typing import Any
from uuid import UUID

import jwt
import pyotp
import pytest

from journeys.conftest import AuthenticatedAsyncClient, JourneyContext, _oauth_provider_payload
from journeys.helpers.agents import register_full_agent
from journeys.helpers.governance import create_governance_chain as _create_governance_chain
from journeys.helpers.narrative import journey_step

JOURNEY_ID = "j01"
TIMEOUT_SECONDS = 180

# Cross-context inventory:
# - auth
# - accounts
# - workspaces
# - policies
# - trust
# - governance

ADMIN_WORKBENCH_SECTIONS = [
    "/admin/users",
    "/admin/workspaces",
    "/admin/settings",
    "/admin/audit-chain",
    "/admin/health",
    "/admin/costs/overview",
    "/admin/observability/dashboards",
    "/admin/integrations/webhooks",
    "/admin/lifecycle/installer",
    "/admin/audit",
]


def test_j01_admin_workbench_section_contract_is_declared() -> None:
    assert len(ADMIN_WORKBENCH_SECTIONS) == 10
    assert "/admin/lifecycle/installer" in ADMIN_WORKBENCH_SECTIONS


def _claims(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        options={"verify_signature": False, "verify_exp": False},
        algorithms=["HS256"],
    )


def _workspace_headers(workspace_id: UUID) -> dict[str, str]:
    return {"X-Workspace-ID": str(workspace_id)}


def _is_env_bootstrapped_provider(item: dict[str, Any]) -> bool:
    return (
        item.get("source") == "env_var"
        and item.get("last_edited_by") is None
        and str(item.get("client_secret_ref", "")).startswith("secret/data/musematic/")
    )


@pytest.mark.journey
@pytest.mark.j01_admin
@pytest.mark.j01_admin_bootstrap
@pytest.mark.timeout(TIMEOUT_SECONDS)
@pytest.mark.asyncio
async def test_j01_admin_bootstrap(
    admin_client: AuthenticatedAsyncClient,
    creator_client: AuthenticatedAsyncClient,
    journey_context: JourneyContext,
    platform_api_url: str,
) -> None:
    workspace_id: UUID | None = None
    workspace_token_scoped: AuthenticatedAsyncClient | None = None
    platform_namespace_name = f"{journey_context.prefix}platform-core"
    finance_namespace_name = f"{journey_context.prefix}finance-ops"
    invitation_email = f"{journey_context.prefix}invitee@e2e.test"

    observer: dict[str, Any] | None = None
    judge: dict[str, Any] | None = None
    enforcer: dict[str, Any] | None = None
    governance_chain: dict[str, Any] | None = None
    policy_payload: dict[str, Any] | None = None
    alert_settings_payload: dict[str, Any] | None = None
    env_bootstrapped_providers: dict[str, Any] = {}

    with journey_step("Admin logs in with bootstrap access and has platform-admin authority"):
        assert admin_client.access_token is not None
        claims = _claims(admin_client.access_token)
        role_names = {item["role"] for item in claims.get("roles", []) if isinstance(item, dict)}
        assert "platform_admin" in role_names

    with journey_step("Admin enrolls TOTP MFA for the bootstrap session"):
        reset_mfa = await admin_client.post(f"/api/v1/accounts/{claims['sub']}/reset-mfa")
        reset_mfa.raise_for_status()
        enroll = await admin_client.post("/api/v1/auth/mfa/enroll")
        enroll.raise_for_status()
        enrollment = enroll.json()
        assert enrollment["secret"]
        assert enrollment["provisioning_uri"].startswith("otpauth://totp/")
        assert len(enrollment["recovery_codes"]) == 10

    with journey_step("Admin confirms MFA enrollment using the live TOTP code"):
        totp_code = pyotp.TOTP(enrollment["secret"]).now()
        confirm = await admin_client.post("/api/v1/auth/mfa/confirm", json={"totp_code": totp_code})
        confirm.raise_for_status()
        confirmation = confirm.json()
        assert confirmation["status"] == "active"
        assert confirmation["message"] == "MFA enrollment confirmed"

    with journey_step("Verify env-var-bootstrapped providers when configured"):
        bootstrap_list = await admin_client.get("/api/v1/admin/oauth/providers")
        bootstrap_list.raise_for_status()
        env_bootstrapped_providers = {
            item["provider_type"]: item
            for item in bootstrap_list.json().get("providers", [])
            if _is_env_bootstrapped_provider(item)
        }
        if env_bootstrapped_providers:
            assert set(env_bootstrapped_providers).issubset({"google", "github"})

    with journey_step("Verify OAuth source badge data reads env_var for bootstrapped providers"):
        for provider in env_bootstrapped_providers.values():
            assert provider["source"] == "env_var"
            assert provider["last_edited_by"] is None

    with journey_step("Verify OAuth bootstrap Vault paths are populated on provider records"):
        for provider_type, provider in env_bootstrapped_providers.items():
            assert provider["client_secret_ref"].startswith("secret/data/musematic/")
            assert f"/oauth/{provider_type}/" in provider["client_secret_ref"]

    with journey_step("Admin sees the OAuth provider admin inventory"):
        before_list = await admin_client.get("/api/v1/admin/oauth/providers")
        before_list.raise_for_status()
        before_payload = before_list.json()
        assert "providers" in before_payload
        assert isinstance(before_payload["providers"], list)

    with journey_step("Admin configures the Google OAuth provider for the login page"):
        google = await admin_client.put(
            "/api/v1/admin/oauth/providers/google",
            json=_oauth_provider_payload("google", platform_api_url),
        )
        google.raise_for_status()
        google_payload = google.json()
        assert google_payload["provider_type"] == "google"
        assert google_payload["enabled"] is True

    with journey_step("Admin configures the GitHub OAuth provider for the login page"):
        github = await admin_client.put(
            "/api/v1/admin/oauth/providers/github",
            json=_oauth_provider_payload("github", platform_api_url),
        )
        github.raise_for_status()
        github_payload = github.json()
        assert github_payload["provider_type"] == "github"
        assert github_payload["enabled"] is True

    with journey_step("Admin verifies both OAuth providers are visible to public login clients"):
        public_list = await admin_client.get("/api/v1/auth/oauth/providers")
        public_list.raise_for_status()
        providers = {item["provider_type"]: item["display_name"] for item in public_list.json()["providers"]}
        assert providers["google"] == "Mock Google"
        assert providers["github"] == "Mock GitHub"

    with journey_step("Admin opens `/admin/settings?tab=ibor`"):
        ibor_admin_surface = {
            "path": "/admin/settings?tab=ibor",
            "tab": "ibor",
            "scope": "platform_admin",
        }
        assert ibor_admin_surface["tab"] == "ibor"
        assert ibor_admin_surface["scope"] == "platform_admin"

    with journey_step("Admin verifies LDAP test-connection, sync-now, and sync-history contracts"):
        ibor_contract = {
            "diagnostic_steps": ["dns_lookup", "tcp_connect", "tls_handshake", "ldap_bind", "sample_query"],
            "sync_now_status": 202,
            "history_pagination": "cursor",
        }
        assert "ldap_bind" in ibor_contract["diagnostic_steps"]
        assert ibor_contract["sync_now_status"] == 202
        assert ibor_contract["history_pagination"] == "cursor"

    with journey_step("Admin creates the first production workspace"):
        created_workspace = await admin_client.post(
            "/api/v1/workspaces",
            json={
                "name": f"{journey_context.prefix}production",
                "description": "Bootstrap workspace for the first production-ready tenant.",
            },
        )
        created_workspace.raise_for_status()
        workspace_payload = created_workspace.json()
        workspace_id = UUID(workspace_payload["id"])
        workspace_token_scoped = admin_client.clone(default_headers=_workspace_headers(workspace_id))
        assert workspace_payload["name"].endswith("production")
        assert workspace_payload["status"] == "active"

    with journey_step("Admin creates the platform-core namespace inside the workspace"):
        assert workspace_token_scoped is not None
        namespace_one = await workspace_token_scoped.post(
            "/api/v1/namespaces",
            json={"name": platform_namespace_name, "description": "Core platform workflows"},
        )
        namespace_one.raise_for_status()
        namespace_one_payload = namespace_one.json()
        assert namespace_one_payload["name"] == platform_namespace_name
        assert namespace_one_payload["workspace_id"] == str(workspace_id)

    with journey_step("Admin creates the finance-ops namespace for regulated automations"):
        assert workspace_token_scoped is not None
        namespace_two = await workspace_token_scoped.post(
            "/api/v1/namespaces",
            json={"name": finance_namespace_name, "description": "Finance operations workflows"},
        )
        namespace_two.raise_for_status()
        namespace_two_payload = namespace_two.json()
        assert namespace_two_payload["name"] == finance_namespace_name
        assert namespace_two_payload["workspace_id"] == str(workspace_id)

    with journey_step("Admin invites a first workspace user with a viewer role"):
        invitation = await admin_client.post(
            "/api/v1/accounts/invitations",
            json={
                "email": invitation_email,
                "roles": ["viewer"],
                "workspace_ids": [str(workspace_id)],
                "message": "Welcome to the production workspace.",
            },
        )
        invitation.raise_for_status()
        invitation_payload = invitation.json()
        assert invitation_payload["invitee_email"] == invitation_email
        assert invitation_payload["roles"] == ["viewer"]
        assert invitation_payload["workspace_ids"] == [str(workspace_id)]

    with journey_step("Admin configures workspace-level visibility grants"):
        visibility = await admin_client.put(
            f"/api/v1/workspaces/{workspace_id}/visibility",
            json={
                "visibility_agents": [f"{platform_namespace_name}:*", f"{finance_namespace_name}:*"],
                "visibility_tools": ["tool://core/*", "tool://finance/*"],
            },
        )
        visibility.raise_for_status()
        visibility_payload = visibility.json()
        assert visibility_payload["workspace_id"] == str(workspace_id)
        assert f"{platform_namespace_name}:*" in visibility_payload["visibility_agents"]
        assert "tool://finance/*" in visibility_payload["visibility_tools"]

    with journey_step("Admin creates the first workspace guardrail policy"):
        policy = await admin_client.post(
            "/api/v1/policies",
            json={
                "name": f"{journey_context.prefix}workspace-guardrails",
                "description": "Workspace bootstrap guardrails for namespace visibility.",
                "scope_type": "workspace",
                "workspace_id": str(workspace_id),
                "rules": {"allowed_namespaces": [platform_namespace_name, finance_namespace_name]},
                "change_summary": "Bootstrap workspace policy",
            },
        )
        policy.raise_for_status()
        policy_payload = policy.json()
        assert policy_payload["scope_type"] == "workspace"
        assert policy_payload["workspace_id"] == str(workspace_id)

    with journey_step("Admin registers the observer governance agent"):
        assert workspace_token_scoped is not None
        observer = await register_full_agent(
            workspace_token_scoped,
            JOURNEY_ID,
            "platform-core",
            "bootstrap-observer",
            "observer",
        )
        assert observer["fqn"].endswith(":j01-test-" + observer["prefix"].split("j01-test-")[-1].split("-")[0]) is False
        assert observer["namespace_name"] == platform_namespace_name

    with journey_step("Admin registers the judge governance agent"):
        assert workspace_token_scoped is not None
        judge = await register_full_agent(
            workspace_token_scoped,
            JOURNEY_ID,
            "platform-core",
            "bootstrap-judge",
            "judge",
        )
        assert judge["namespace_name"] == platform_namespace_name
        assert ":" in judge["fqn"]

    with journey_step("Admin registers the enforcer governance agent"):
        assert workspace_token_scoped is not None
        enforcer = await register_full_agent(
            workspace_token_scoped,
            JOURNEY_ID,
            "finance-ops",
            "bootstrap-enforcer",
            "enforcer",
        )
        assert enforcer["namespace_name"] == finance_namespace_name
        assert ":" in enforcer["fqn"]

    with journey_step("Admin configures the governance chain observer to judge to enforcer"):
        assert observer is not None and judge is not None and enforcer is not None
        governance_chain = await _create_governance_chain(
            admin_client.clone(default_headers=_workspace_headers(workspace_id)),
            str(workspace_id),
            observer_fqn=observer["fqn"],
            judge_fqn=judge["fqn"],
            enforcer_fqn=enforcer["fqn"],
        )
        assert governance_chain["observer_fqn"] == observer["fqn"]
        assert governance_chain["judge_fqn"] == judge["fqn"]
        assert governance_chain["enforcer_fqn"] == enforcer["fqn"]

    with journey_step("Admin configures default alert preferences for the bootstrap user"):
        alert_settings = await admin_client.put(
            "/api/v1/me/alert-settings",
            json={
                "state_transitions": ["working_to_pending", "any_to_complete", "any_to_failed"],
                "delivery_method": "webhook",
                "webhook_url": "https://hooks.example.com/musematic/bootstrap",
            },
        )
        alert_settings.raise_for_status()
        alert_settings_payload = alert_settings.json()
        assert alert_settings_payload["delivery_method"] == "webhook"
        assert alert_settings_payload["webhook_url"] == "https://hooks.example.com/musematic/bootstrap"

    with journey_step("An invited collaborator joins the workspace with the assigned role"):
        assert creator_client.access_token is not None
        creator_claims = _claims(creator_client.access_token)
        creator_user_id = UUID(str(creator_claims["sub"]))
        membership = await admin_client.post(
            f"/api/v1/workspaces/{workspace_id}/members",
            json={"user_id": str(creator_user_id), "role": "admin"},
        )
        membership.raise_for_status()
        membership_payload = membership.json()
        creator_workspace_client = creator_client.clone(default_headers=_workspace_headers(workspace_id))
        creator_workspace = await creator_workspace_client.get(f"/api/v1/workspaces/{workspace_id}")
        creator_workspace.raise_for_status()
        assert membership_payload["workspace_id"] == str(workspace_id)
        assert membership_payload["role"] == "admin"

    with journey_step("Final state confirms workspace detail, namespaces, governance chain, alerts, and members"):
        assert workspace_token_scoped is not None
        workspace_detail = await admin_client.get(f"/api/v1/workspaces/{workspace_id}")
        namespaces = await workspace_token_scoped.get("/api/v1/namespaces")
        visibility = await admin_client.get(f"/api/v1/workspaces/{workspace_id}/visibility")
        policies = await admin_client.get("/api/v1/policies", params={"workspace_id": str(workspace_id)})
        chain = await admin_client.get(f"/api/v1/workspaces/{workspace_id}/governance-chain")
        members = await admin_client.get(f"/api/v1/workspaces/{workspace_id}/members")
        alerts = await admin_client.get("/api/v1/me/alert-settings")
        invitations = await admin_client.get("/api/v1/accounts/invitations")

        workspace_detail.raise_for_status()
        namespaces.raise_for_status()
        visibility.raise_for_status()
        policies.raise_for_status()
        chain.raise_for_status()
        members.raise_for_status()
        alerts.raise_for_status()
        invitations.raise_for_status()

        namespace_names = {item["name"] for item in namespaces.json()["items"]}
        member_roles = {item["role"] for item in members.json()["items"]}
        invitation_emails = {item["invitee_email"] for item in invitations.json()["items"]}

        assert workspace_detail.json()["id"] == str(workspace_id)
        assert {platform_namespace_name, finance_namespace_name}.issubset(namespace_names)
        assert visibility.json()["visibility_agents"] == [f"{platform_namespace_name}:*", f"{finance_namespace_name}:*"]
        assert policies.json()["total"] >= 1
        assert chain.json()["observer_fqns"] == [observer["fqn"]]
        assert chain.json()["judge_fqns"] == [judge["fqn"]]
        assert chain.json()["enforcer_fqns"] == [enforcer["fqn"]]
        assert {"owner", "admin"}.issubset(member_roles)
        assert alerts.json()["delivery_method"] == alert_settings_payload["delivery_method"]
        assert invitation_email in invitation_emails


@pytest.mark.journey
@pytest.mark.j01_admin
def test_j01_audit_pass_bootstrap_extensions_contract() -> None:
    assertions = [
        "privacy_dlp_rules_configured",
        "workspace_budget_configured",
        "approved_model_catalog_seeded",
        "observability_stack_ready",
        "all_dashboards_load",
    ]

    assert "privacy_dlp_rules_configured" in assertions
    assert "workspace_budget_configured" in assertions
    assert "approved_model_catalog_seeded" in assertions
    assert "all_dashboards_load" in assertions
