"""UPD-053 (106) US6 — local smoke test for the helm-snapshot drift gate.

Catches the "developer changed the chart but forgot ``make
helm-snapshot-update``" failure mode locally instead of waiting for CI.

The test runs the snapshot regenerator and asserts the working tree
remains clean afterwards. If it fails, run ``make helm-snapshot-update``
and commit the regenerated files in the same PR as the chart change.

Skip-marked when ``helm`` is unavailable so this test doesn't fail in
slim dev shells; CI installs helm via ``azure/setup-helm``.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = REPO_ROOT / "deploy" / "helm" / "platform" / ".snapshots"


pytestmark = pytest.mark.skipif(
    shutil.which("helm") is None,
    reason="helm is not on PATH; CI installs it via azure/setup-helm.",
)


def _git_status_porcelain(paths: list[Path]) -> str:
    """Return ``git status --porcelain`` output limited to the given paths.

    The ``-z`` flag is intentionally avoided — we want a human-readable
    diff in the error message. The ``--`` sentinel separates paths from
    flags. Output is empty when the paths are clean.
    """
    cmd = ["git", "status", "--porcelain", "--"] + [str(p) for p in paths]
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


@pytest.mark.skipif(
    os.environ.get("RUN_HELM_SNAPSHOT_DRIFT", "0") != "1",
    reason=(
        "Slow (~30s) — opt-in via RUN_HELM_SNAPSHOT_DRIFT=1 locally. CI "
        "runs the snapshot-diff gate inline in the helm-lint job."
    ),
)
def test_helm_snapshot_regenerates_to_clean_tree() -> None:
    """``make helm-snapshot-update`` against a clean working tree must
    yield a clean working tree afterwards.
    """
    pre_status = _git_status_porcelain([SNAPSHOT_DIR])
    assert pre_status == "", (
        "Snapshot directory is dirty before regeneration; commit or "
        "stash existing changes first.\n" + pre_status
    )

    subprocess.run(
        ["make", "helm-snapshot-update"],
        cwd=REPO_ROOT,
        check=True,
    )

    post_status = _git_status_porcelain([SNAPSHOT_DIR])
    assert post_status == "", (
        "Snapshot drift detected after `make helm-snapshot-update`. The "
        "committed snapshots disagree with what the current chart "
        "renders. Run `make helm-snapshot-update` locally, review the "
        "diff in deploy/helm/platform/.snapshots/, and commit the "
        "regenerated files alongside the chart change.\n" + post_status
    )
