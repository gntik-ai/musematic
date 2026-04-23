from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from platform.auth.schemas import TokenPair
from platform.auth.services.oauth_service import OAuthService
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
from uuid import UUID, uuid4

from tests.auth_support import FakeAsyncRedisClient, RecordingProducer


def build_provider(
    *,
    provider_type: str = "google",
    enabled: bool = True,
    require_mfa: bool = False,
    group_role_mapping: dict[str, str] | None = None,
    domain_restrictions: list[str] | None = None,
    org_restrictions: list[str] | None = None,
) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        provider_type=provider_type,
        display_name="Google" if provider_type == "google" else "GitHub",
        enabled=enabled,
        client_id=f"{provider_type}-client",
        client_secret_ref=f"plain:{provider_type}-secret",
        redirect_uri=f"https://app.example.com/oauth/{provider_type}/callback",
        scopes=["openid", "email", "profile"]
        if provider_type == "google"
        else ["read:user", "user:email"],
        domain_restrictions=list(domain_restrictions or []),
        org_restrictions=list(org_restrictions or []),
        group_role_mapping=dict(group_role_mapping or {}),
        default_role="viewer",
        require_mfa=require_mfa,
        created_at=now,
        updated_at=now,
    )


@dataclass
class OAuthRepositoryStub:
    providers: dict[str, Any] = field(default_factory=dict)
    links_by_external: dict[tuple[UUID, str], Any] = field(default_factory=dict)
    links_by_user_provider: dict[tuple[UUID, UUID], Any] = field(default_factory=dict)
    links_by_user: dict[UUID, list[Any]] = field(default_factory=dict)
    audit_entries: list[dict[str, Any]] = field(default_factory=list)
    upsert_calls: list[dict[str, Any]] = field(default_factory=list)
    deleted_links: list[Any] = field(default_factory=list)
    auth_method_count: int = 2

    async def get_provider_by_type(self, provider_type: str) -> Any | None:
        return self.providers.get(provider_type)

    async def get_all_providers(self) -> list[Any]:
        return list(self.providers.values())

    async def upsert_provider(self, provider_type: str, **kwargs: Any) -> tuple[Any, bool]:
        self.upsert_calls.append({"provider_type": provider_type, **kwargs})
        provider = self.providers.get(provider_type)
        created = provider is None
        if provider is None:
            provider = build_provider(provider_type=provider_type)
            self.providers[provider_type] = provider
        for key, value in kwargs.items():
            setattr(provider, key, value)
        provider.updated_at = datetime.now(UTC)
        return provider, created

    async def get_link_by_external(self, provider_id: UUID, external_id: str) -> Any | None:
        return self.links_by_external.get((provider_id, external_id))

    async def get_link_for_user_provider(self, user_id: UUID, provider_id: UUID) -> Any | None:
        return self.links_by_user_provider.get((user_id, provider_id))

    async def get_links_for_user(self, user_id: UUID) -> list[Any]:
        return list(self.links_by_user.get(user_id, []))

    async def create_link(self, **kwargs: Any) -> Any:
        payload = dict(kwargs)
        last_login_at = payload.pop("last_login_at", None)
        link = SimpleNamespace(
            id=uuid4(),
            linked_at=datetime.now(UTC),
            last_login_at=last_login_at,
            provider=None,
            **payload,
        )
        self.links_by_external[(kwargs["provider_id"], kwargs["external_id"])] = link
        self.links_by_user_provider[(kwargs["user_id"], kwargs["provider_id"])] = link
        self.links_by_user.setdefault(kwargs["user_id"], []).append(link)
        return link

    async def update_link(self, link: Any, **kwargs: Any) -> Any:
        for key, value in kwargs.items():
            setattr(link, key, value)
        return link

    async def delete_link(self, link: Any) -> None:
        self.deleted_links.append(link)
        self.links_by_external.pop((link.provider_id, link.external_id), None)
        self.links_by_user_provider.pop((link.user_id, link.provider_id), None)
        self.links_by_user[link.user_id] = [
            item for item in self.links_by_user.get(link.user_id, []) if item is not link
        ]

    async def count_auth_methods(self, user_id: UUID) -> int:
        del user_id
        return self.auth_method_count

    async def create_audit_entry(self, **kwargs: Any) -> Any:
        entry = {"id": uuid4(), "created_at": datetime.now(UTC), **kwargs}
        self.audit_entries.append(entry)
        return SimpleNamespace(**entry)

    async def list_audit_entries(self, **kwargs: Any) -> list[Any]:
        del kwargs
        return [SimpleNamespace(**item) for item in self.audit_entries]


@dataclass
class AuthRepositoryStub:
    users_by_email: dict[str, Any] = field(default_factory=dict)
    users_by_id: dict[UUID, Any] = field(default_factory=dict)
    roles_by_user: dict[UUID, list[Any]] = field(default_factory=dict)
    enrollments_by_user: dict[UUID, Any] = field(default_factory=dict)
    credentials_by_user: dict[UUID, Any] = field(default_factory=dict)
    credentials_by_email: dict[str, Any] = field(default_factory=dict)
    assigned_roles: list[tuple[UUID, str, UUID | None]] = field(default_factory=list)

    async def get_platform_user_by_email(self, email: str) -> Any | None:
        return self.users_by_email.get(email.lower())

    async def get_platform_user(self, user_id: UUID) -> Any | None:
        return self.users_by_id.get(user_id)

    async def assign_user_role(self, user_id: UUID, role: str, workspace_id: UUID | None) -> Any:
        assignment = SimpleNamespace(user_id=user_id, role=role, workspace_id=workspace_id)
        self.assigned_roles.append((user_id, role, workspace_id))
        self.roles_by_user.setdefault(user_id, []).append(assignment)
        return assignment

    async def get_user_roles(self, user_id: UUID, workspace_id: UUID | None) -> list[Any]:
        del workspace_id
        return list(self.roles_by_user.get(user_id, []))

    async def get_mfa_enrollment(self, user_id: UUID) -> Any | None:
        return self.enrollments_by_user.get(user_id)

    async def get_credential_by_user_id(self, user_id: UUID) -> Any | None:
        return self.credentials_by_user.get(user_id)

    async def get_credential_by_email(self, email: str) -> Any | None:
        return self.credentials_by_email.get(email.lower())

    async def ensure_credential(
        self,
        user_id: UUID,
        email: str,
        password_hash: str,
    ) -> Any:
        normalized_email = email.lower()
        credential = self.credentials_by_user.get(user_id)
        if credential is None:
            credential = SimpleNamespace(
                user_id=user_id,
                email=normalized_email,
                password_hash=password_hash,
                is_active=True,
            )
            self.credentials_by_user[user_id] = credential
            self.credentials_by_email[normalized_email] = credential
        return credential


@dataclass
class AccountsRepositoryStub:
    created_users: list[Any] = field(default_factory=list)
    updated_users: list[tuple[UUID, Any, dict[str, Any]]] = field(default_factory=list)
    platform_registry: AuthRepositoryStub | None = None

    async def create_user(
        self, *, email: str, display_name: str, status: Any, signup_source: Any
    ) -> Any:
        user = SimpleNamespace(
            id=uuid4(),
            email=email.lower(),
            display_name=display_name,
            status=status,
            signup_source=signup_source,
        )
        self.created_users.append(user)
        if self.platform_registry is not None:
            platform_user = SimpleNamespace(
                id=user.id,
                email=user.email,
                display_name=user.display_name,
                status="active",
            )
            self.platform_registry.users_by_id[user.id] = platform_user
            self.platform_registry.users_by_email[user.email] = platform_user
        return user

    async def update_user_status(self, user_id: UUID, status: Any, **kwargs: Any) -> Any:
        self.updated_users.append((user_id, status, kwargs))
        return SimpleNamespace(id=user_id, status=status, **kwargs)


@dataclass
class GoogleProviderStub:
    identity: dict[str, Any] = field(
        default_factory=lambda: {
            "sub": "google-subject",
            "email": "alex@example.com",
            "name": "Alex Example",
            "picture": "https://images.example.com/alex.png",
            "aud": "google-client",
            "email_verified": "true",
        }
    )
    groups: list[str] = field(default_factory=list)
    auth_urls: list[dict[str, Any]] = field(default_factory=list)
    exchanged_codes: list[dict[str, Any]] = field(default_factory=list)

    def get_auth_url(self, **kwargs: Any) -> str:
        self.auth_urls.append(kwargs)
        return f"https://accounts.google.test/auth?{urlencode(kwargs, doseq=True)}"

    async def exchange_code(self, **kwargs: Any) -> dict[str, Any]:
        self.exchanged_codes.append(kwargs)
        return {"id_token": "google-id-token", "access_token": "google-access-token"}

    async def fetch_user(self, *, id_token: str, client_id: str) -> dict[str, Any]:
        assert id_token == "google-id-token"
        assert client_id
        return dict(self.identity)

    async def fetch_groups(self, *, access_token: str) -> list[str]:
        assert access_token == "google-access-token"
        return list(self.groups)


@dataclass
class GitHubProviderStub:
    user_payload: dict[str, Any] = field(
        default_factory=lambda: {
            "id": 123,
            "login": "octocat",
            "name": "Octo Cat",
            "avatar_url": "https://images.example.com/octocat.png",
        }
    )
    email: str = "octocat@example.com"
    teams: list[str] = field(default_factory=list)
    memberships: dict[str, bool] = field(default_factory=dict)
    auth_urls: list[dict[str, Any]] = field(default_factory=list)

    def get_auth_url(self, **kwargs: Any) -> str:
        self.auth_urls.append(kwargs)
        return f"https://github.test/login/oauth/authorize?{urlencode(kwargs, doseq=True)}"

    async def exchange_code(self, **kwargs: Any) -> dict[str, Any]:
        return {"access_token": "github-access-token"}

    async def fetch_user(self, *, access_token: str) -> dict[str, Any]:
        assert access_token == "github-access-token"
        return dict(self.user_payload)

    async def fetch_emails(self, *, access_token: str) -> str:
        assert access_token == "github-access-token"
        return self.email

    async def check_org_membership(self, *, access_token: str, org: str) -> bool:
        assert access_token == "github-access-token"
        return self.memberships.get(org, False)

    async def fetch_teams(self, *, access_token: str, orgs: list[str]) -> list[str]:
        assert access_token == "github-access-token"
        del orgs
        return list(self.teams)


@dataclass
class AuthServiceStub:
    token_pair: TokenPair = field(
        default_factory=lambda: TokenPair(
            access_token="access-token",
            refresh_token="refresh-token",
            expires_in=900,
        )
    )
    session_calls: list[dict[str, Any]] = field(default_factory=list)
    challenge_calls: list[dict[str, Any]] = field(default_factory=list)

    async def create_session(self, **kwargs: Any) -> TokenPair:
        self.session_calls.append(kwargs)
        return self.token_pair

    async def create_pending_mfa_challenge(self, **kwargs: Any) -> Any:
        self.challenge_calls.append(kwargs)
        return SimpleNamespace(mfa_token="oauth-mfa-token")


@dataclass
class RateLimitResultStub:
    allowed: bool
    retry_after_ms: int = 0


class RateLimitRedisStub(FakeAsyncRedisClient):
    def __init__(self, result: RateLimitResultStub) -> None:
        super().__init__()
        self.result = result
        self.calls: list[tuple[str, str, int, int]] = []

    async def check_rate_limit(
        self, scope: str, key: str, maximum: int, window_ms: int
    ) -> RateLimitResultStub:
        self.calls.append((scope, key, maximum, window_ms))
        return self.result


def build_oauth_service_fixture(
    auth_settings: Any,
    *,
    provider: Any | None = None,
    google_provider: GoogleProviderStub | None = None,
    github_provider: GitHubProviderStub | None = None,
    repository: OAuthRepositoryStub | None = None,
    auth_repository: AuthRepositoryStub | None = None,
    accounts_repository: AccountsRepositoryStub | None = None,
    redis_client: FakeAsyncRedisClient | None = None,
    auth_service: AuthServiceStub | None = None,
    producer: RecordingProducer | None = None,
    credential_resolver: Any | None = None,
) -> tuple[
    OAuthService,
    OAuthRepositoryStub,
    AuthRepositoryStub,
    AccountsRepositoryStub,
    FakeAsyncRedisClient,
    RecordingProducer,
    AuthServiceStub,
]:
    provider = provider or build_provider()
    repository = repository or OAuthRepositoryStub(providers={provider.provider_type: provider})
    auth_repository = auth_repository or AuthRepositoryStub()
    accounts_repository = accounts_repository or AccountsRepositoryStub(
        platform_registry=auth_repository
    )
    redis_client = redis_client or FakeAsyncRedisClient()
    producer = producer or RecordingProducer()
    auth_service = auth_service or AuthServiceStub()
    service = OAuthService(
        repository=repository,
        auth_repository=auth_repository,
        accounts_repository=accounts_repository,
        redis_client=redis_client,
        settings=auth_settings,
        producer=producer,
        auth_service=auth_service,
        google_provider=google_provider or GoogleProviderStub(),
        github_provider=github_provider or GitHubProviderStub(),
        credential_resolver=credential_resolver,
    )
    return (
        service,
        repository,
        auth_repository,
        accounts_repository,
        redis_client,
        producer,
        auth_service,
    )


def extract_query_param(url: str, name: str) -> str:
    values = parse_qs(urlparse(url).query).get(name, [])
    if not values:
        raise AssertionError(f"missing query param: {name}")
    return values[0]


def decode_fragment_payload(fragment: str) -> dict[str, Any]:
    token = urlparse(f"https://example.test/{fragment}").fragment.split("=", 1)[1]
    padding = "=" * (-len(token) % 4)
    raw = token + padding
    return json.loads(__import__("base64").urlsafe_b64decode(raw.encode("utf-8")).decode("utf-8"))
