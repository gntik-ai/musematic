from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from tests.integration.privacy_compliance.helpers import (
    Ed25519Signer,
    build_orchestrator,
    populated_stores,
    run_dsr,
)

pytestmark = pytest.mark.integration

VERIFIER = (
    Path(__file__).resolve().parents[5]
    / "tests/e2e/scripts/verify_signed_tombstone.py"
)


@pytest.mark.asyncio
async def test_signed_tombstone_external_verify_reimplements_hash_and_signature(tmp_path) -> None:
    subject_user_id = uuid4()
    signer = Ed25519Signer()
    orchestrator, _repository, _adapters = build_orchestrator(
        stores=populated_stores(subject_user_id),
        signer=signer,
    )
    result = await run_dsr(
        orchestrator,
        dsr_id=uuid4(),
        subject_user_id=subject_user_id,
    )
    signed = await orchestrator.export_signed(result.tombstone.id)

    tombstone_payload = json.loads(signed.tombstone)
    external_canonical = json.dumps(
        {
            "cascade_log": sorted(
                tombstone_payload["cascade_log"],
                key=lambda item: str(item.get("started_at_iso", item.get("store_name", ""))),
            ),
            "created_at_iso": tombstone_payload["created_at_iso"],
            "entities_deleted": dict(sorted(tombstone_payload["entities_deleted"].items())),
            "salt_version": tombstone_payload["salt_version"],
            "subject_user_id_hash": tombstone_payload["subject_user_id_hash"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    signed_path = tmp_path / "signed-tombstone.json"
    signed_path.write_text(
        json.dumps(
            {
                "tombstone": external_canonical,
                "signature": signed.signature,
                "proof_hash": signed.proof_hash,
            }
        )
    )

    assert hashlib.sha256(external_canonical.encode("utf-8")).hexdigest() == (
        result.tombstone.proof_hash
    )
    assert signed.proof_hash == result.tombstone.proof_hash
    assert base64.b64decode(signed.signature)

    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(VERIFIER),
        str(signed_path),
        "--public-key",
        signer.public_key_pem(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    assert process.returncode == 0, stderr.decode("utf-8")
    assert "signed tombstone verified" in stdout.decode("utf-8")
