from __future__ import annotations

import tarfile
from io import BytesIO
from pathlib import Path
from typing import Any

from journeys.helpers import fixtures_dir, journey_resource_prefix


def _package_path() -> Path:
    return fixtures_dir() / "agent_package.tar.gz"


def _manifest_bytes(
    *,
    local_name: str,
    role_type: str,
    purpose: str,
    approach: str | None,
    manifest_kwargs: dict[str, Any],
) -> bytes:
    import json

    payload = {
        "local_name": local_name,
        "version": manifest_kwargs.pop("version", "1.0.0"),
        "purpose": purpose,
        "role_types": manifest_kwargs.pop("role_types", [role_type]),
        "approach": approach,
        "maturity_level": manifest_kwargs.pop("maturity_level", 1),
        "reasoning_modes": manifest_kwargs.pop("reasoning_modes", ["deterministic"]),
        "tags": manifest_kwargs.pop("tags", ["journey", local_name]),
        "display_name": manifest_kwargs.pop(
            "display_name", local_name.replace("-", " ").title()
        ),
    }
    payload.update(manifest_kwargs)
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")


def _build_package_from_stub(
    *,
    local_name: str,
    role_type: str,
    purpose: str,
    approach: str | None,
    manifest_kwargs: dict[str, Any],
) -> bytes:
    buffer = BytesIO()
    manifest_bytes = _manifest_bytes(
        local_name=local_name,
        role_type=role_type,
        purpose=purpose,
        approach=approach,
        manifest_kwargs=dict(manifest_kwargs),
    )

    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        manifest = tarfile.TarInfo(name="manifest.json")
        manifest.size = len(manifest_bytes)
        archive.addfile(manifest, BytesIO(manifest_bytes))

        stub = _package_path()
        if stub.exists():
            with tarfile.open(stub, mode="r:gz") as existing:
                for member in existing.getmembers():
                    if member.name in {"manifest.yaml", "manifest.json"} or not member.isfile():
                        continue
                    extracted = existing.extractfile(member)
                    if extracted is None:
                        continue
                    content = extracted.read()
                    cloned = tarfile.TarInfo(name=member.name)
                    cloned.size = len(content)
                    archive.addfile(cloned, BytesIO(content))
    return buffer.getvalue()


async def _ensure_namespace(client, namespace_name: str) -> dict[str, Any]:
    response = await client.post("/api/v1/namespaces", json={"name": namespace_name})
    if response.status_code in {200, 201}:
        return response.json()
    if response.status_code not in {400, 409}:
        response.raise_for_status()

    listed = await client.get("/api/v1/namespaces")
    listed.raise_for_status()
    items = listed.json().get("items", [])
    for item in items:
        if item.get("name") == namespace_name:
            return item
    raise AssertionError(f"namespace {namespace_name} could not be created or discovered")


async def register_full_agent(
    client,
    journey_id: str,
    namespace: str,
    local_name: str,
    role_type: str,
    **manifest_kwargs,
) -> dict[str, Any]:
    prefix = journey_resource_prefix(journey_id)
    namespace_name = f"{prefix}{namespace}".lower()[:63]
    agent_local_name = f"{prefix}{local_name}".lower()[:63]
    await _ensure_namespace(client, namespace_name)

    purpose = manifest_kwargs.pop(
        "purpose",
        "Journey-created agent used to validate end-to-end platform capabilities safely.",
    )
    approach = manifest_kwargs.pop(
        "approach",
        "Exercises the registry, trust, and orchestration flows with deterministic fixtures.",
    )
    package_bytes = _build_package_from_stub(
        local_name=agent_local_name,
        role_type=role_type,
        purpose=purpose,
        approach=approach,
        manifest_kwargs=manifest_kwargs,
    )

    files = {
        "package": ("agent_package.tar.gz", package_bytes, "application/gzip"),
    }
    data = {"namespace_name": namespace_name}
    upload = await client.post("/api/v1/agents/upload", data=data, files=files)
    upload.raise_for_status()
    payload = upload.json()
    profile = payload["agent_profile"]
    revision = payload["revision"]
    return {
        "id": profile["id"],
        "fqn": profile["fqn"],
        "namespace_name": namespace_name,
        "local_name": agent_local_name,
        "revision_id": revision["id"],
        "profile": profile,
        "revision": revision,
        "prefix": prefix,
    }


async def certify_agent(
    client,
    agent_id: str,
    reviewer_client=None,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    operator = reviewer_client or client
    agent = await client.get(f"/api/v1/agents/{agent_id}")
    agent.raise_for_status()
    profile = agent.json()
    revision = profile.get("current_revision")
    if revision is None:
        raise AssertionError(f"agent {agent_id} does not have a current revision")

    created = await operator.post(
        "/api/v1/trust/certifications",
        json={
            "agent_id": str(profile["id"]),
            "agent_fqn": profile["fqn"],
            "agent_revision_id": str(revision["id"]),
        },
    )
    created.raise_for_status()
    certification = created.json()

    for index, item in enumerate(evidence or [], start=1):
        attached = await operator.post(
            f"/api/v1/trust/certifications/{certification['id']}/evidence",
            json={
                "evidence_type": "test_results",
                "source_ref_type": "journey_step",
                "source_ref_id": f"evidence-{index}",
                "summary": item,
            },
        )
        attached.raise_for_status()

    activated = await operator.post(
        f"/api/v1/trust/certifications/{certification['id']}/activate"
    )
    activated.raise_for_status()
    result = activated.json()
    return {
        "certification_id": result["id"],
        "status": result["status"],
        "certification": result,
    }
