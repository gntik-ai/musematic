from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_platform_chart_exists_for_e2e_bootstrap() -> None:
    chart = ROOT / 'deploy/helm/platform/Chart.yaml'
    assert chart.exists(), chart
    contents = chart.read_text()
    assert 'alias: controlPlane' in contents
    assert 'name: reasoning-engine' in contents


def test_kind_config_is_parameterized_for_parallel_clusters() -> None:
    config = (ROOT / 'tests/e2e/cluster/kind-config.yaml').read_text()
    assert '${CLUSTER_NAME}' in config
    assert '${PORT_UI}' in config
    assert '${PORT_API}' in config
    assert '${PORT_WS}' in config


def test_install_script_bootstraps_cluster_operators_and_platform_chart() -> None:
    install_script = (ROOT / 'tests/e2e/cluster/install.sh').read_text()
    assert 'install_cnpg_operator' in install_script
    assert 'install_strimzi_operator' in install_script
    assert 'helm dependency build' in install_script
    assert 'helm upgrade --install' in install_script
    assert 'python3 -m seeders.base --all' in install_script


def test_makefile_renders_cluster_specific_kind_config() -> None:
    makefile = (ROOT / 'tests/e2e/Makefile').read_text()
    assert 'render-kind-config' in makefile
    assert 'envsubst < $(KIND_CONFIG_TEMPLATE) > $(KIND_CONFIG_RENDERED)' in makefile
    assert 'PLATFORM_API_URL ?= http://localhost:$(PORT_API)' in makefile
    assert 'PLATFORM_WS_URL ?= ws://localhost:$(PORT_WS)' in makefile


def test_load_images_uses_repo_root_context_for_ui_build() -> None:
    load_images = (ROOT / 'tests/e2e/cluster/load-images.sh').read_text()
    assert 'ghcr.io/musematic/ui:local|apps/web/Dockerfile|.' in load_images
    assert 'docker build -t "${image}" -f "${ROOT_DIR}/${dockerfile}" "${ROOT_DIR}/${context}"' in load_images
