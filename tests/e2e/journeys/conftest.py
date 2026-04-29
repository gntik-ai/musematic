from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_DNS, UUID, uuid4, uuid5

import httpx
import jwt
import pytest
import pytest_asyncio
import websockets

from journeys.helpers import journey_resource_prefix
from journeys.helpers.agents import certify_agent, register_full_agent
from journeys.helpers.api_waits import wait_for_policy, wait_for_workspace_access
from journeys.helpers.axe_runner import run_axe_scan
from journeys.helpers.governance import create_governance_chain
from journeys.helpers.observability_readiness import (
    _grafana_url,
    _jaeger_url,
    _loki_url,
    _prom_url,
    wait_for_observability_stack_ready,
)
from journeys.helpers.oauth import oauth_login

pytest_plugins = ["journeys.plugins.narrative_report"]

_SESSION_ADMIN_BEARER_TOKEN: str | None = None
_REQUIRED_CONSENT_CHOICES = {
    "ai_interaction": True,
    "data_collection": True,
    "training_use": True,
}

_PERSONA_SPECS: dict[str, dict[str, Any]] = {
    "admin": {
        "email": "j-admin@e2e.test",
        "roles": ["platform_admin"],
    },
    "operator": {
        "email": "j-operator@e2e.test",
        "roles": ["platform_operator", "platform_admin"],
    },
    "trust_reviewer": {
        "email": "j-trust-reviewer@e2e.test",
        "roles": ["trust_reviewer", "trust_certifier"],
    },
    "evaluator": {
        "email": "j-evaluator@e2e.test",
        "roles": ["evaluator"],
    },
    "researcher": {
        "email": "j-researcher@e2e.test",
        "roles": ["researcher"],
    },
}


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)



def _bool_env(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}



def _jwt_secret() -> str:
    return _env("AUTH_JWT_SECRET_KEY", "change-me")



def _jwt_algorithm() -> str:
    return _env("AUTH_JWT_ALGORITHM", "HS256")



def _persona_email(persona: str) -> str:
    return str(_PERSONA_SPECS[persona]["email"])



def _persona_roles(persona: str) -> list[str]:
    return list(_PERSONA_SPECS[persona]["roles"])



def _persona_user_id(persona: str) -> UUID:
    return uuid5(NAMESPACE_DNS, f"journey-persona:{persona}:{_persona_email(persona)}")



def _normalize_roles(role_names: list[str], workspace_id: UUID | None = None) -> list[dict[str, str | None]]:
    normalized: list[dict[str, str | None]] = []
    seen: set[tuple[str, str | None]] = set()
    workspace_value = str(workspace_id) if workspace_id is not None else None
    for role_name in role_names:
        key = (role_name, workspace_value)
        if key in seen:
            continue
        normalized.append({"role": role_name, "workspace_id": workspace_value})
        seen.add(key)
    return normalized



def _mint_access_token(
    *,
    user_id: UUID,
    email: str,
    role_names: list[str],
    workspace_id: UUID | None = None,
    permissions: list[str] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "roles": _normalize_roles(role_names, workspace_id=workspace_id),
        "session_id": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=8)).timestamp()),
        "type": "access",
        "identity_type": "user",
    }
    if workspace_id is not None:
        payload["workspace_id"] = str(workspace_id)
    if permissions:
        payload["permissions"] = list(permissions)
    return jwt.encode(payload, _jwt_secret(), algorithm=_jwt_algorithm())


def _decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        options={"verify_signature": False, "verify_exp": False},
        algorithms=[_jwt_algorithm()],
    )


@dataclass(slots=True)
class JourneyContext:
    journey_id: str
    nodeid: str
    prefix: str


@dataclass(slots=True)
class OAuthProvisionedIdentity:
    user_id: UUID
    email: str


class AuthenticatedAsyncClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.raw_client = httpx.AsyncClient(
            base_url=base_url,
            follow_redirects=False,
            timeout=timeout,
        )
        self.timeout = timeout
        self.default_headers = dict(default_headers or {})
        self.access_token: str | None = None
        self.refresh_token: str | None = None

    async def __aenter__(self) -> AuthenticatedAsyncClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self.raw_client.aclose()

    def clone(
        self,
        *,
        default_headers: dict[str, str] | None = None,
    ) -> AuthenticatedAsyncClient:
        cloned = AuthenticatedAsyncClient(
            str(self.raw_client.base_url),
            timeout=self.timeout,
            default_headers=default_headers if default_headers is not None else dict(self.default_headers),
        )
        cloned.access_token = self.access_token
        cloned.refresh_token = self.refresh_token
        return cloned

    def set_bearer_token(self, token: str) -> None:
        self.access_token = token

    def _headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        merged = dict(self.default_headers)
        merged.update(headers or {})
        if self.access_token:
            merged.setdefault("Authorization", f"Bearer {self.access_token}")
        return merged

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        headers = self._headers(kwargs.pop("headers", None))
        return await self.raw_client.request(method, url, headers=headers, **kwargs)

    async def get(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("DELETE", url, **kwargs)

    async def login(
        self,
        email: str,
        password: str,
        *,
        totp_code: str | None = None,
    ) -> dict[str, Any]:
        response = await self.post("/api/v1/auth/login", json={"email": email, "password": password})
        response.raise_for_status()
        payload = response.json()
        if payload.get("mfa_required"):
            if not totp_code:
                raise AssertionError(f"login for {email} requires MFA but no TOTP code was supplied")
            verify = await self.post(
                "/api/v1/auth/mfa/verify",
                json={"mfa_token": payload["mfa_token"], "totp_code": totp_code},
            )
            verify.raise_for_status()
            payload = verify.json()
        token = payload.get("access_token")
        if not token:
            raise AssertionError(f"login for {email} did not return an access token")
        self.set_bearer_token(token)
        refresh_token = payload.get("refresh_token")
        self.refresh_token = refresh_token if isinstance(refresh_token, str) else None
        return payload


class JourneyWsClient:
    def __init__(self, url: str, *, access_token: str | None = None) -> None:
        self.url = url
        self.access_token = access_token

    def _connect_url(self) -> str:
        normalized = self.url.rstrip('/')
        if normalized.endswith('/ws'):
            return normalized
        return f"{normalized}/ws"

    async def connect(self):
        headers = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return await websockets.connect(self._connect_url(), additional_headers=headers)



def _oauth_provider_payload(provider: str, platform_api_url: str) -> dict[str, Any]:
    if provider == "google":
        return {
            "display_name": "Mock Google",
            "enabled": True,
            "client_id": _env("JOURNEY_GOOGLE_CLIENT_ID", "mock-google-client-id"),
            "client_secret_ref": _env(
                "JOURNEY_GOOGLE_CLIENT_SECRET_REF",
                "plain:mock-google-client-secret",
            ),
            "redirect_uri": f"{platform_api_url.rstrip('/')}/api/v1/auth/oauth/google/callback",
            "scopes": ["openid", "email", "profile"],
            "domain_restrictions": [],
            "org_restrictions": [],
            "group_role_mapping": {},
            "default_role": "workspace_member",
            "require_mfa": False,
        }
    if provider == "github":
        return {
            "display_name": "Mock GitHub",
            "enabled": True,
            "client_id": _env("JOURNEY_GITHUB_CLIENT_ID", "mock-github-client-id"),
            "client_secret_ref": _env(
                "JOURNEY_GITHUB_CLIENT_SECRET_REF",
                "plain:mock-github-client-secret",
            ),
            "redirect_uri": f"{platform_api_url.rstrip('/')}/api/v1/auth/oauth/github/callback",
            "scopes": ["read:user", "user:email"],
            "domain_restrictions": [],
            "org_restrictions": [],
            "group_role_mapping": {},
            "default_role": "workspace_admin",
            "require_mfa": False,
        }
    raise AssertionError(f"unsupported oauth provider bootstrap: {provider}")



def _use_password_login(persona_key: str) -> bool:
    return _bool_env(f"JOURNEY_{persona_key.upper()}_USE_PASSWORD_LOGIN") or _bool_env(
        "JOURNEY_USE_PASSWORD_LOGIN"
    )


async def _password_login_client(
    http_client: AuthenticatedAsyncClient,
    *,
    email_env: str,
    password_env: str,
    totp_env: str | None = None,
    default_email: str,
    default_password: str = "JourneyPassword1!",
) -> AuthenticatedAsyncClient:
    client = http_client.clone()
    await client.login(
        _env(email_env, default_email),
        _env(password_env, default_password),
        totp_code=_env(totp_env, "") if totp_env else None,
    )
    await _grant_required_consents(client)
    return client


async def _grant_required_consents(
    client: AuthenticatedAsyncClient,
    *,
    workspace_id: UUID | None = None,
) -> None:
    payload: dict[str, Any] = {"choices": dict(_REQUIRED_CONSENT_CHOICES)}
    if workspace_id is not None:
        payload["workspace_id"] = str(workspace_id)
    response: httpx.Response | None = None
    for attempt in range(5):
        response = await client.put("/api/v1/me/consents", json=payload)
        if response.status_code not in {429, 503}:
            break
        retry_after = response.headers.get("Retry-After")
        try:
            delay = float(retry_after) if retry_after else 0.5 * (attempt + 1)
        except ValueError:
            delay = 0.5 * (attempt + 1)
        await asyncio.sleep(min(delay, 2.0))
    assert response is not None
    response.raise_for_status()


def _minted_persona_client(
    http_client: AuthenticatedAsyncClient,
    persona: str,
    *,
    workspace_id: UUID | None = None,
    extra_roles: list[str] | None = None,
    permissions: list[str] | None = None,
    user_id: UUID | None = None,
    email: str | None = None,
) -> AuthenticatedAsyncClient:
    client = http_client.clone(
        default_headers=(
            {"X-Workspace-ID": str(workspace_id)} if workspace_id is not None else None
        )
    )
    role_names = _persona_roles(persona)
    if extra_roles:
        role_names = [*role_names, *extra_roles]
    token = _mint_access_token(
        user_id=user_id or _persona_user_id(persona),
        email=email or _persona_email(persona),
        role_names=role_names,
        workspace_id=workspace_id,
        permissions=permissions,
    )
    client.set_bearer_token(token)
    return client


def _scoped_persona_client(
    http_client: AuthenticatedAsyncClient,
    persona: str,
    *,
    workspace_id: UUID,
    extra_roles: list[str] | None = None,
    permissions: list[str] | None = None,
) -> AuthenticatedAsyncClient:
    if http_client.access_token is None:
        raise AssertionError(f"{persona} client must be authenticated before scoping")
    claims = _decode_access_token(http_client.access_token)
    return _minted_persona_client(
        http_client,
        persona,
        workspace_id=workspace_id,
        extra_roles=extra_roles,
        permissions=permissions,
        user_id=UUID(str(claims["sub"])),
        email=str(claims.get("email") or _persona_email(persona)),
    )


def _register_cleanup(request: pytest.FixtureRequest, item: dict[str, Any]) -> None:
    cleanup_items = getattr(request.node, "_journey_cleanup", None)
    if cleanup_items is None:
        cleanup_items = []
        setattr(request.node, "_journey_cleanup", cleanup_items)
    cleanup_items.append(item)


async def _cleanup_workspace(platform_api_url: str, workspace_id: str, token: str) -> None:
    async with AuthenticatedAsyncClient(platform_api_url) as client:
        client.set_bearer_token(token)
        archive = await client.post(f"/api/v1/workspaces/{workspace_id}/archive")
        if archive.status_code not in {200, 404, 409}:
            archive.raise_for_status()
        delete = await client.delete(f"/api/v1/workspaces/{workspace_id}")
        if delete.status_code not in {202, 404, 409}:
            delete.raise_for_status()


async def _create_workspace_policy(
    client: AuthenticatedAsyncClient,
    *,
    workspace_id: UUID,
    name: str,
    description: str,
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/policies",
        json={
            "name": name,
            "description": description,
            "scope_type": "workspace",
            "workspace_id": str(workspace_id),
            "rules": {},
            "change_summary": "Journey bootstrap policy",
        },
    )
    response.raise_for_status()
    policy = response.json()
    return await wait_for_policy(client, policy["id"])


async def _list_namespace_by_name(
    client: AuthenticatedAsyncClient,
    namespace_name: str,
) -> dict[str, Any]:
    response = await client.get("/api/v1/namespaces")
    response.raise_for_status()
    items = response.json().get("items", [])
    for item in items:
        if item.get("name") == namespace_name:
            return item
    raise AssertionError(f"namespace {namespace_name} was not found after registration")


async def _transition_agent_status(
    client: AuthenticatedAsyncClient,
    *,
    agent_id: str,
    target_status: str,
    reason: str,
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/agents/{agent_id}/transition",
        json={"target_status": target_status, "reason": reason},
    )
    response.raise_for_status()
    return response.json()


async def _update_agent_maturity(
    client: AuthenticatedAsyncClient,
    *,
    agent_id: str,
    maturity_level: int,
    reason: str,
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/agents/{agent_id}/maturity",
        json={"maturity_level": maturity_level, "reason": reason},
    )
    response.raise_for_status()
    return response.json()


async def _attach_policy_to_revision(
    client: AuthenticatedAsyncClient,
    *,
    policy_id: str,
    revision_id: str,
) -> dict[str, Any]:
    await wait_for_policy(client, policy_id)
    response = await client.post(
        f"/api/v1/policies/{policy_id}/attach",
        json={
            "target_type": "agent_revision",
            "target_id": str(revision_id),
        },
    )
    response.raise_for_status()
    return response.json()



def _workflow_yaml(agent_fqn: str) -> str:
    return f"""schema_version: 1
steps:
  - id: run_agent
    step_type: agent_task
    agent_fqn: {agent_fqn}
    input_bindings:
      journey: $.input.journey
""".strip()


@pytest.fixture(scope="session")
def mock_google_oidc() -> str:
    return _env("MOCK_GOOGLE_OIDC_URL", "http://localhost:8083")


@pytest.fixture(scope="session")
def mock_github_oauth() -> str:
    return _env("MOCK_GITHUB_OAUTH_URL", "http://localhost:8084")


@pytest.fixture(scope="session")
def journeys_reports_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def journey_id(request) -> str:
    return str(getattr(request.module, "JOURNEY_ID", "unknown"))


@pytest.fixture(scope="session")
def observability_stack_ready() -> None:
    asyncio.run(wait_for_observability_stack_ready())


@pytest.fixture
def journey_context(
    request,
    journey_id: str,
    observability_stack_ready: None,
) -> JourneyContext:
    del observability_stack_ready
    return JourneyContext(
        journey_id=journey_id,
        nodeid=request.node.nodeid,
        prefix=journey_resource_prefix(journey_id, nodeid=request.node.nodeid),
    )


@pytest_asyncio.fixture
async def loki_client(observability_stack_ready: None):
    del observability_stack_ready
    async with httpx.AsyncClient(base_url=_loki_url(), timeout=30.0) as client:
        yield client


@pytest_asyncio.fixture
async def prom_client(observability_stack_ready: None):
    del observability_stack_ready
    async with httpx.AsyncClient(base_url=_prom_url(), timeout=30.0) as client:
        yield client


@pytest_asyncio.fixture
async def jaeger_client(observability_stack_ready: None):
    del observability_stack_ready
    async with httpx.AsyncClient(base_url=_jaeger_url(), timeout=30.0) as client:
        yield client


@pytest_asyncio.fixture
async def grafana_client(observability_stack_ready: None):
    del observability_stack_ready
    async with httpx.AsyncClient(base_url=_grafana_url(), timeout=30.0) as client:
        yield client


@pytest.fixture
def axe_runner():
    return run_axe_scan


@pytest_asyncio.fixture
async def http_client(platform_api_url: str):
    async with AuthenticatedAsyncClient(platform_api_url) as client:
        yield client


@pytest_asyncio.fixture(scope="session", autouse=True)
async def ensure_journey_personas(platform_api_url: str) -> dict[str, str]:
    global _SESSION_ADMIN_BEARER_TOKEN

    admin_token = _mint_access_token(
        user_id=_persona_user_id("admin"),
        email=_persona_email("admin"),
        role_names=_persona_roles("admin"),
    )
    _SESSION_ADMIN_BEARER_TOKEN = admin_token
    os.environ["JOURNEY_ADMIN_BEARER_TOKEN"] = admin_token

    try:
        async with AuthenticatedAsyncClient(platform_api_url) as client:
            client.set_bearer_token(admin_token)
            for provider in ("google", "github"):
                response = await client.put(
                    f"/api/v1/admin/oauth/providers/{provider}",
                    json=_oauth_provider_payload(provider, platform_api_url),
                )
                response.raise_for_status()
            listed = await client.get("/api/v1/auth/oauth/providers")
            listed.raise_for_status()
            providers = {
                item["provider_type"]: item["display_name"]
                for item in listed.json().get("providers", [])
            }
    except httpx.RequestError:
        return {}
    return providers


@pytest_asyncio.fixture(scope="session")
async def admin_oauth_identity(
    platform_api_url: str,
    mock_google_oidc: str,
    ensure_journey_personas: dict[str, str],
) -> OAuthProvisionedIdentity:
    del ensure_journey_personas
    if _use_password_login("admin"):
        return OAuthProvisionedIdentity(
            user_id=_persona_user_id("admin"),
            email=_persona_email("admin"),
        )

    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
    async with AuthenticatedAsyncClient(platform_api_url) as client:
        provisioned = await oauth_login(
            client,
            provider="google",
            mock_server=mock_google_oidc,
            login=_env("JOURNEY_ADMIN_GOOGLE_LOGIN", f"{worker_id}-admin"),
        )
        assert provisioned.access_token is not None
        claims = _decode_access_token(provisioned.access_token)
        await _grant_required_consents(provisioned)
        return OAuthProvisionedIdentity(
            user_id=UUID(str(claims["sub"])),
            email=str(claims.get("email") or _persona_email("admin")),
        )


@pytest_asyncio.fixture(autouse=True)
async def cleanup_journey_resources(
    request: pytest.FixtureRequest,
    platform_api_url: str,
) -> None:
    setattr(request.node, "_journey_cleanup", [])
    yield

    cleanup_items = list(reversed(getattr(request.node, "_journey_cleanup", [])))
    for item in cleanup_items:
        if item.get("kind") == "workspace":
            token = str(item.get("token") or "")
            workspace_id = str(item.get("workspace_id") or "")
            if token and workspace_id:
                await _cleanup_workspace(platform_api_url, workspace_id, token)

    if not _bool_env("JOURNEY_ENABLE_CLEANUP", default=False):
        return
    token = _SESSION_ADMIN_BEARER_TOKEN or os.environ.get("JOURNEY_ADMIN_BEARER_TOKEN")
    if not token:
        return
    async with httpx.AsyncClient(base_url=platform_api_url, timeout=30.0) as client:
        headers = {"Authorization": f"Bearer {token}"}
        for scope in ("executions", "workspaces"):
            await client.post(
                "/api/v1/_e2e/reset",
                json={"scope": scope, "include_baseline": False},
                headers=headers,
            )


@pytest_asyncio.fixture
async def admin_client(
    http_client: AuthenticatedAsyncClient,
    ensure_journey_personas: dict[str, str],
    admin_oauth_identity: OAuthProvisionedIdentity,
) -> AuthenticatedAsyncClient:
    del ensure_journey_personas
    if _use_password_login("admin"):
        return await _password_login_client(
            http_client,
            email_env="JOURNEY_ADMIN_EMAIL",
            password_env="JOURNEY_ADMIN_PASSWORD",
            totp_env="JOURNEY_ADMIN_TOTP_CODE",
            default_email=_persona_email("admin"),
        )

    # The backing account is provisioned once per xdist worker through OAuth;
    # each test then receives a fresh elevated journey token for isolation.
    token = _mint_access_token(
        user_id=admin_oauth_identity.user_id,
        email=admin_oauth_identity.email,
        role_names=_persona_roles("admin"),
    )
    client = http_client.clone()
    client.set_bearer_token(token)
    await _grant_required_consents(client)
    return client


@pytest_asyncio.fixture
async def operator_client(
    http_client: AuthenticatedAsyncClient,
    ensure_journey_personas: dict[str, str],
) -> AuthenticatedAsyncClient:
    del ensure_journey_personas
    if _use_password_login("operator"):
        return await _password_login_client(
            http_client,
            email_env="JOURNEY_OPERATOR_EMAIL",
            password_env="JOURNEY_OPERATOR_PASSWORD",
            default_email=_persona_email("operator"),
        )
    return _minted_persona_client(
        http_client,
        "operator",
        permissions=["execution.rollback"],
    )


@pytest_asyncio.fixture
async def trust_reviewer_client(
    http_client: AuthenticatedAsyncClient,
    ensure_journey_personas: dict[str, str],
) -> AuthenticatedAsyncClient:
    del ensure_journey_personas
    if _use_password_login("trust_reviewer"):
        return await _password_login_client(
            http_client,
            email_env="JOURNEY_TRUST_REVIEWER_EMAIL",
            password_env="JOURNEY_TRUST_REVIEWER_PASSWORD",
            default_email=_persona_email("trust_reviewer"),
        )
    return _minted_persona_client(http_client, "trust_reviewer")


@pytest_asyncio.fixture
async def evaluator_client(
    http_client: AuthenticatedAsyncClient,
    ensure_journey_personas: dict[str, str],
) -> AuthenticatedAsyncClient:
    del ensure_journey_personas
    if _use_password_login("evaluator"):
        return await _password_login_client(
            http_client,
            email_env="JOURNEY_EVALUATOR_EMAIL",
            password_env="JOURNEY_EVALUATOR_PASSWORD",
            default_email=_persona_email("evaluator"),
        )
    return _minted_persona_client(http_client, "evaluator")


@pytest_asyncio.fixture
async def researcher_client(
    http_client: AuthenticatedAsyncClient,
    ensure_journey_personas: dict[str, str],
) -> AuthenticatedAsyncClient:
    del ensure_journey_personas
    if _use_password_login("researcher"):
        return await _password_login_client(
            http_client,
            email_env="JOURNEY_RESEARCHER_EMAIL",
            password_env="JOURNEY_RESEARCHER_PASSWORD",
            default_email=_persona_email("researcher"),
        )
    return _minted_persona_client(http_client, "researcher")


@pytest_asyncio.fixture
async def creator_client(
    http_client: AuthenticatedAsyncClient,
    mock_github_oauth: str,
    ensure_journey_personas: dict[str, str],
    journey_context: JourneyContext,
) -> AuthenticatedAsyncClient:
    del ensure_journey_personas
    client = http_client.clone()
    authenticated = await oauth_login(
        client,
        provider="github",
        mock_server=mock_github_oauth,
        login=_env("JOURNEY_CREATOR_GITHUB_LOGIN", f"{journey_context.journey_id}-creator-gh"),
    )
    await _grant_required_consents(authenticated)
    return authenticated


@pytest_asyncio.fixture
async def consumer_client(
    http_client: AuthenticatedAsyncClient,
    mock_google_oidc: str,
    ensure_journey_personas: dict[str, str],
    journey_context: JourneyContext,
) -> AuthenticatedAsyncClient:
    del ensure_journey_personas
    client = http_client.clone()
    authenticated = await oauth_login(
        client,
        provider="google",
        mock_server=mock_google_oidc,
        login=_env("JOURNEY_CONSUMER_GOOGLE_LOGIN", f"{journey_context.journey_id}-consumer"),
    )
    await _grant_required_consents(authenticated)
    return authenticated


@pytest.fixture
def ws_client(platform_ws_url: str, admin_client: AuthenticatedAsyncClient) -> JourneyWsClient:
    return JourneyWsClient(platform_ws_url, access_token=admin_client.access_token)


@pytest_asyncio.fixture
async def workspace_with_agents(
    request: pytest.FixtureRequest,
    admin_client: AuthenticatedAsyncClient,
    journey_context: JourneyContext,
) -> dict[str, Any]:
    workspace = await admin_client.post(
        "/api/v1/workspaces",
        json={
            "name": f"{journey_context.prefix}ws-primary",
            "description": "Journey bootstrap workspace with governance-ready agents.",
        },
    )
    workspace.raise_for_status()
    workspace_payload = workspace.json()
    workspace_id = UUID(str(workspace_payload["id"]))
    workspace_payload = await wait_for_workspace_access(admin_client, workspace_id)
    _register_cleanup(
        request,
        {
            "kind": "workspace",
            "workspace_id": str(workspace_id),
            "token": admin_client.access_token,
        },
    )

    scoped_admin = _scoped_persona_client(
        http_client=admin_client,
        persona="admin",
        workspace_id=workspace_id,
    )
    try:
        agent_specs = [
            ("ops", "executor", "executor"),
            ("ops", "observer", "observer"),
            ("ops", "judge", "judge"),
            ("ops", "enforcer", "enforcer"),
        ]
        agents: dict[str, dict[str, Any]] = {}
        for namespace, local_name, role_type in agent_specs:
            agents[local_name] = await register_full_agent(
                scoped_admin,
                journey_context.journey_id,
                namespace,
                local_name,
                role_type,
                purpose="Journey helper agent used to seed a workspace with governance and orchestration coverage.",
            )

        namespace_payload = await _list_namespace_by_name(
            scoped_admin,
            agents["executor"]["namespace_name"],
        )

        default_allow = await _create_workspace_policy(
            scoped_admin,
            workspace_id=workspace_id,
            name=f"{journey_context.prefix}default-allow",
            description="Journey default allow policy for workspace-scoped agent bootstrapping.",
        )
        finance_strict = await _create_workspace_policy(
            scoped_admin,
            workspace_id=workspace_id,
            name=f"{journey_context.prefix}finance-strict",
            description="Journey secondary policy used for later trust and enforcement coverage.",
        )
        default_allow_attachment = await _attach_policy_to_revision(
            scoped_admin,
            policy_id=str(default_allow["id"]),
            revision_id=str(agents["executor"]["revision_id"]),
        )
        governance_chain = await create_governance_chain(
            scoped_admin,
            str(workspace_id),
            observer_fqn=agents["observer"]["fqn"],
            judge_fqn=agents["judge"]["fqn"],
            enforcer_fqn=agents["enforcer"]["fqn"],
        )
        return {
            "workspace": workspace_payload,
            "workspace_id": str(workspace_id),
            "headers": {"X-Workspace-ID": str(workspace_id)},
            "namespace": namespace_payload,
            "agents": agents,
            "policies": {
                "default-allow": default_allow,
                "finance-strict": finance_strict,
            },
            "policy_attachments": {
                "default-allow-executor": default_allow_attachment,
            },
            "governance_chain": governance_chain,
        }
    finally:
        await scoped_admin.aclose()


@pytest_asyncio.fixture
async def published_agent(
    admin_client: AuthenticatedAsyncClient,
    workspace_with_agents: dict[str, Any],
    journey_context: JourneyContext,
) -> dict[str, Any]:
    workspace_id = UUID(workspace_with_agents["workspace_id"])
    scoped_admin = _scoped_persona_client(
        http_client=admin_client,
        persona="admin",
        workspace_id=workspace_id,
    )
    try:
        published = await register_full_agent(
            scoped_admin,
            journey_context.journey_id,
            "marketplace",
            "published-agent",
            "executor",
            purpose="Journey published agent fixture used to validate publication and marketplace flows end to end.",
            tags=["journey", "marketplace", "published"],
            display_name="Journey Published Agent",
        )
        patch = await scoped_admin.patch(
            f"/api/v1/agents/{published['id']}",
            json={
                "display_name": "Journey Published Agent",
                "approach": "Provides deterministic marketplace coverage for end-to-end journeys.",
                "tags": ["journey", "marketplace", "published"],
                "visibility_agents": ["*"],
                "visibility_tools": ["*"],
            },
        )
        patch.raise_for_status()
        policy_attachment = await _attach_policy_to_revision(
            scoped_admin,
            policy_id=str(workspace_with_agents["policies"]["default-allow"]["id"]),
            revision_id=str(published["revision_id"]),
        )
        certification = await certify_agent(
            scoped_admin,
            published["id"],
            evidence=["Journey bootstrap evidence attached automatically."],
        )
        validated = await _transition_agent_status(
            scoped_admin,
            agent_id=str(published["id"]),
            target_status="validated",
            reason="Journey fixture validated prior to publication.",
        )
        maturity = await _update_agent_maturity(
            scoped_admin,
            agent_id=str(published["id"]),
            maturity_level=3,
            reason="Journey fixture certified and ready for publication.",
        )
        published_status = await _transition_agent_status(
            scoped_admin,
            agent_id=str(published["id"]),
            target_status="published",
            reason="Journey fixture published for marketplace discovery.",
        )
        listing = await scoped_admin.get(f"/api/v1/marketplace/agents/{published['id']}")
        listing.raise_for_status()
        return {
            **published,
            "workspace_id": str(workspace_id),
            "headers": {"X-Workspace-ID": str(workspace_id)},
            "policy_attachment": policy_attachment,
            "certification": certification,
            "validated": validated,
            "maturity": maturity,
            "published": published_status,
            "marketplace_listing": listing.json(),
        }
    finally:
        await scoped_admin.aclose()


@pytest_asyncio.fixture
async def workspace_with_goal_ready(
    admin_client: AuthenticatedAsyncClient,
    workspace_with_agents: dict[str, Any],
    journey_context: JourneyContext,
) -> dict[str, Any]:
    workspace_id = UUID(workspace_with_agents["workspace_id"])
    scoped_admin = _scoped_persona_client(
        http_client=admin_client,
        persona="admin",
        workspace_id=workspace_id,
    )
    try:
        agent_specs = [
            ("collab", "market-data-agent", "executor", {"keywords": ["market", "portfolio"]}),
            ("collab", "risk-analysis-agent", "executor", {"keywords": ["risk", "hedge"]}),
            ("collab", "client-advisory-agent", "executor", {"keywords": ["client", "advisory"]}),
            ("collab", "notification-agent", "executor", {"keywords": ["notifications"]}),
        ]
        subscribed_agents: list[str] = []
        decision_configs: dict[str, dict[str, Any]] = {}
        agents: dict[str, dict[str, Any]] = {}
        for namespace, local_name, role_type, config in agent_specs:
            agent = await register_full_agent(
                scoped_admin,
                journey_context.journey_id,
                namespace,
                local_name,
                role_type,
                purpose="Journey collaboration agent used to exercise workspace-goal routing decisions.",
            )
            agents[local_name] = agent
            subscribed_agents.append(agent["fqn"])
            decision_configs[agent["fqn"]] = config

        settings = await scoped_admin.patch(
            f"/api/v1/workspaces/{workspace_id}/settings",
            json={"subscribed_agents": subscribed_agents},
        )
        settings.raise_for_status()

        configured_decisions: dict[str, Any] = {}
        for agent_fqn, config in decision_configs.items():
            response = await scoped_admin.put(
                f"/api/v1/workspaces/{workspace_id}/agent-decision-configs/{agent_fqn}",
                json={
                    "response_decision_strategy": "keyword",
                    "response_decision_config": {"keywords": config["keywords"], "mode": "any_of"},
                },
            )
            response.raise_for_status()
            configured_decisions[agent_fqn] = response.json()

        goal = await scoped_admin.post(
            f"/api/v1/workspaces/{workspace_id}/goals",
            json={
                "title": f"{journey_context.prefix}goal-ready",
                "description": "Journey goal prepared for collaborative workspace flows.",
                "auto_complete_timeout_seconds": 600,
            },
        )
        goal.raise_for_status()
        return {
            **workspace_with_agents,
            "goal": goal.json(),
            "subscribed_agents": subscribed_agents,
            "goal_agents": agents,
            "agent_decision_configs": configured_decisions,
            "settings": settings.json(),
        }
    finally:
        await scoped_admin.aclose()


@pytest_asyncio.fixture
async def running_workload(
    admin_client: AuthenticatedAsyncClient,
    workspace_with_agents: dict[str, Any],
    journey_context: JourneyContext,
) -> dict[str, Any]:
    workspace_id = UUID(workspace_with_agents["workspace_id"])
    scoped_admin = _scoped_persona_client(
        http_client=admin_client,
        persona="admin",
        workspace_id=workspace_id,
    )
    try:
        workload_agents = [
            await register_full_agent(
                scoped_admin,
                journey_context.journey_id,
                "workload",
                name,
                role_type,
                purpose="Journey workload agent used to seed fleet and execution pressure.",
            )
            for name, role_type in (
                ("lead-planner", "planner"),
                ("exec-worker-a", "executor"),
                ("exec-worker-b", "executor"),
            )
        ]
        fleet = await scoped_admin.post(
            "/api/v1/fleets",
            json={
                "name": f"{journey_context.prefix}fleet",
                "topology_type": "peer_to_peer",
                "quorum_min": 1,
                "topology_config": {},
                "member_fqns": [item["fqn"] for item in workload_agents],
            },
        )
        fleet.raise_for_status()
        fleet_payload = fleet.json()

        warm_pool_config = await admin_client.put(
            "/api/v1/runtime/warm-pool/config",
            json={
                "workspace_id": str(workspace_id),
                "agent_type": "executor",
                "target_size": 2,
            },
        )
        warm_pool_config.raise_for_status()
        warm_pool_config_payload = warm_pool_config.json()
        warm_pool_status = await admin_client.get(
            "/api/v1/runtime/warm-pool/status",
            params={"workspace_id": str(workspace_id), "agent_type": "executor"},
        )
        if warm_pool_status.status_code == 200:
            warm_pool_payload = warm_pool_status.json()
        elif warm_pool_status.status_code >= 500:
            target_size = int(warm_pool_config_payload.get("target_size", 0))
            warm_pool_payload = {
                "ready": 0,
                "capacity": target_size,
                "available_pods": 0,
                "pool_size": target_size,
                "status": "unavailable",
                "error": warm_pool_status.text[:200],
            }
        else:
            warm_pool_status.raise_for_status()
            warm_pool_payload = warm_pool_status.json()

        workflow = await scoped_admin.post(
            "/api/v1/workflows",
            json={
                "name": f"{journey_context.prefix}operator-workload",
                "description": "Journey operator workload seed workflow.",
                "yaml_source": _workflow_yaml(workload_agents[1]["fqn"]),
                "tags": ["journey", "operator"],
                "workspace_id": str(workspace_id),
            },
        )
        workflow.raise_for_status()
        workflow_payload = workflow.json()

        executions: list[dict[str, Any]] = []
        for index in range(5):
            created = await scoped_admin.post(
                "/api/v1/executions",
                json={
                    "workflow_definition_id": str(workflow_payload["id"]),
                    "workspace_id": str(workspace_id),
                    "trigger_type": "manual",
                    "input_parameters": {"batch": index + 1, "journey": journey_context.journey_id},
                    "correlation_fleet_id": str(fleet_payload["id"]),
                },
            )
            created.raise_for_status()
            executions.append(created.json())

        active_executions = [
            item for item in executions if item.get("status") in {"running", "waiting_for_approval"}
        ]
        queued_executions = [item for item in executions if item.get("status") == "queued"]
        if len(active_executions) < 2:
            active_executions = executions[:2]
        if len(queued_executions) < 3:
            queued_executions = executions[-3:]

        return {
            **workspace_with_agents,
            "fleet": fleet_payload,
            "workload_agents": workload_agents,
            "workflow": workflow_payload,
            "active_executions": active_executions,
            "queued_executions": queued_executions,
            "warm_pool": warm_pool_payload,
            "warm_pool_config": warm_pool_config_payload,
        }
    finally:
        await scoped_admin.aclose()



def pytest_configure(config) -> None:
    for marker, description in (
        ("journey", "marks a user journey test"),
        ("j01_admin", "admin bootstrap journey"),
        ("j01_admin_bootstrap", "full admin bootstrap journey"),
        ("j02_creator", "creator to publication journey"),
        ("j02_creator_to_publication", "full creator to publication journey"),
        ("j03_consumer", "consumer discovery and execution journey"),
        ("j03_consumer_discovery_execution", "full consumer discovery and execution journey"),
        ("j04_workspace_goal", "workspace goal collaboration journey"),
        ("j04_workspace_goal_collaboration", "full workspace goal collaboration journey"),
        ("j05_trust", "trust governance pipeline journey"),
        ("j05_trust_governance_pipeline", "full trust governance pipeline journey"),
        ("j06_operator", "operator incident response journey"),
        ("j06_operator_incident_response", "full operator incident response journey"),
        ("j07_evaluator", "evaluator improvement loop journey"),
        ("j07_evaluator_improvement_loop", "full evaluator improvement loop journey"),
        ("j08_external", "external A2A and MCP journey"),
        ("j08_external_a2a_mcp", "full external A2A and MCP journey"),
        ("j09_discovery", "scientific discovery journey"),
        ("j09_scientific_discovery", "full scientific discovery journey"),
        ("j10_notifications", "multi-channel notifications journey"),
        ("j10_multi_channel_notifications", "full multi-channel notifications journey"),
    ):
        config.addinivalue_line("markers", f"{marker}: {description}")
