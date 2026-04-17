from __future__ import annotations

from pathlib import Path

from platform_cli.checkpoint.manager import CheckpointManager, InstallStepStatus
from platform_cli.config import InstallerConfig


def test_checkpoint_create_update_and_load_latest(tmp_path: Path) -> None:
    manager = CheckpointManager(base_dir=tmp_path)
    config = InstallerConfig()
    checkpoint = manager.create(config, ["preflight", "deploy"])

    assert checkpoint.install_id
    assert manager.get_resume_point() == "preflight"

    manager.update_step("preflight", InstallStepStatus.IN_PROGRESS)
    manager.update_step("preflight", InstallStepStatus.COMPLETED)
    manager.update_step("deploy", InstallStepStatus.IN_PROGRESS)
    manager.update_step("deploy", InstallStepStatus.FAILED, error="boom")
    manager.update_metadata(jaeger_runtime="docker", jaeger_process_pid=321)

    loaded = manager.load_latest(manager.compute_config_hash(config))

    assert loaded is not None
    assert loaded.steps[0].status == InstallStepStatus.COMPLETED
    assert loaded.steps[1].status == InstallStepStatus.FAILED
    assert loaded.metadata["jaeger_runtime"] == "docker"
    assert loaded.metadata["jaeger_process_pid"] == "321"
    assert manager.get_resume_point() == "deploy"
    assert manager.checkpoint_path is not None
    assert manager.checkpoint is not None
