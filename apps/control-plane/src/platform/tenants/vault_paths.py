from __future__ import annotations

import re

_ENVIRONMENTS = frozenset({"production", "staging", "dev", "test", "ci", "local"})
_DOMAINS = frozenset(
    {
        "oauth",
        "model-providers",
        "notifications",
        "ibor",
        "audit-chain",
        "connectors",
        "accounts",
        "_internal",
    }
)
_SLUG_RE = re.compile(r"^(default|[a-z][a-z0-9-]{0,30}[a-z0-9])$")
_RESOURCE_RE = re.compile(r"^[A-Za-z0-9_./-]+$")


def tenant_vault_path(env: str, tenant_slug: str, domain: str, resource: str) -> str:
    env = _validate_env(env)
    tenant_slug = _validate_slug(tenant_slug)
    domain = _validate_domain(domain)
    resource = _validate_resource(resource)
    return f"secret/data/musematic/{env}/tenants/{tenant_slug}/{domain}/{resource}"


def platform_vault_path(env: str, domain: str, resource: str) -> str:
    env = _validate_env(env)
    domain = _validate_domain(domain)
    resource = _validate_resource(resource)
    return f"secret/data/musematic/{env}/_platform/{domain}/{resource}"


def legacy_vault_path(env: str, domain: str, resource: str) -> str:
    env = _validate_env(env)
    domain = _validate_domain(domain)
    resource = _validate_resource(resource)
    return f"secret/data/musematic/{env}/{domain}/{resource}"


def _validate_env(env: str) -> str:
    if env not in _ENVIRONMENTS:
        raise ValueError(f"unsupported Vault environment: {env}")
    return env


def _validate_slug(slug: str) -> str:
    if not _SLUG_RE.fullmatch(slug):
        raise ValueError(f"invalid tenant slug for Vault path: {slug}")
    return slug


def _validate_domain(domain: str) -> str:
    if domain not in _DOMAINS:
        raise ValueError(f"unsupported Vault domain: {domain}")
    return domain


def _validate_resource(resource: str) -> str:
    if not resource or resource.startswith("/") or ".." in resource:
        raise ValueError("Vault resource must be a relative path without parent traversal")
    if not _RESOURCE_RE.fullmatch(resource):
        raise ValueError(f"invalid Vault resource path: {resource}")
    return resource
