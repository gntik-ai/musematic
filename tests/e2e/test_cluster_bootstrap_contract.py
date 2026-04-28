from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _load_yaml(relative_path: str) -> dict[str, Any]:
    values = yaml.safe_load((ROOT / relative_path).read_text())
    assert isinstance(values, dict)
    return values


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


def test_operator_installs_use_server_side_apply_for_large_crds() -> None:
    install_script = (ROOT / 'tests/e2e/cluster/install.sh').read_text()
    assert 'kubectl apply --server-side=true --force-conflicts -f "${CNPG_MANIFEST_URL}"' in install_script
    assert 'kubectl apply --server-side=true --force-conflicts -n strimzi-system -f "${STRIMZI_MANIFEST_URL}"' in install_script


def test_observability_install_adds_helm_repositories_before_dependency_build() -> None:
    install_script = (ROOT / 'tests/e2e/cluster/install.sh').read_text()
    observability_install = install_script.split('install_observability() {', 1)[1].split(
        '\n}\n\nwait_for_labelled_pod',
        1,
    )[0]

    assert 'ensure_observability_helm_repos' in install_script
    assert 'https://open-telemetry.github.io/opentelemetry-helm-charts' in install_script
    assert 'https://prometheus-community.github.io/helm-charts' in install_script
    assert 'https://jaegertracing.github.io/helm-charts' in install_script
    assert 'https://grafana.github.io/helm-charts' in install_script
    assert observability_install.index('ensure_observability_helm_repos') < observability_install.index(
        'helm dependency build "${OBSERVABILITY_CHART_DIR}"',
    )


def test_observability_install_uses_targeted_readiness_after_helm_apply() -> None:
    install_script = (ROOT / 'tests/e2e/cluster/install.sh').read_text()
    observability_install = install_script.split('install_observability() {', 1)[1].split(
        '\n}\n\nwait_for_labelled_pod',
        1,
    )[0]
    observability_wait = install_script.split('wait_for_observability_stack() {', 1)[1].split(
        '\n}\n\nstart_observability_port_forward',
        1,
    )[0]

    assert '--wait' not in observability_install
    assert observability_install.index('--timeout "${HELM_TIMEOUT}"') < observability_install.index(
        'wait_for_observability_stack "${PLATFORM_READY_TIMEOUT}"',
    )
    assert 'wait_for_labelled_pod "${OBSERVABILITY_NAMESPACE}" "$selector" "$timeout"' in observability_wait


def test_observability_loki_port_forward_probe_uses_gateway_supported_path() -> None:
    install_script = (ROOT / 'tests/e2e/cluster/install.sh').read_text()
    port_forward_section = install_script.split('start_observability_port_forwards() {', 1)[1].split(
        '\n}\n\nensure_observability_helm_repos',
        1,
    )[0]

    assert 'probe_observability_http loki "http://localhost:3100/loki/api/v1/status/buildinfo"' in port_forward_section
    assert 'probe_observability_http loki "http://localhost:3100/ready"' not in port_forward_section


def test_journey_observability_helpers_use_gateway_supported_loki_probe() -> None:
    readiness_helper = (ROOT / 'tests/e2e/journeys/helpers/observability_readiness.py').read_text()
    log_helper = (ROOT / 'tests/e2e/journeys/helpers/assert_log_entry.py').read_text()

    assert 'LOKI_READY_PATH = "/loki/api/v1/status/buildinfo"' in readiness_helper
    assert '"loki": (_loki_url(), LOKI_READY_PATH)' in readiness_helper
    assert 'loki_client.get(LOKI_READY_PATH)' in log_helper
    assert 'loki_client.get("/ready")' not in log_helper


def test_loki_alerts_require_lokirule_crd_capability() -> None:
    loki_alerts = (ROOT / 'deploy/helm/observability/templates/alerts/loki-alerts.yaml').read_text()

    assert loki_alerts.startswith('{{- if .Capabilities.APIVersions.Has "loki.grafana.com/v1/LokiRule" }}')
    assert loki_alerts.rstrip().endswith('{{- end }}')


def test_observability_namespace_creation_is_gated_for_helm_create_namespace() -> None:
    template = (ROOT / 'deploy/helm/observability/templates/namespace.yaml').read_text()
    values = _load_yaml('deploy/helm/observability/values.yaml')
    e2e_values = _load_yaml('deploy/helm/observability/values-e2e.yaml')

    assert template.startswith('{{- if .Values.createNamespace }}')
    assert template.rstrip().endswith('{{- end }}')
    assert values['createNamespace'] is False
    assert e2e_values['createNamespace'] is False


def test_e2e_observability_loki_uses_kind_sized_ephemeral_storage() -> None:
    e2e_values = _load_yaml('deploy/helm/observability/values-e2e.yaml')
    loki = e2e_values['loki']

    assert loki['singleBinary']['persistence']['enabled'] is False
    assert {'name': 'loki-data', 'emptyDir': {}} in loki['singleBinary']['extraVolumes']
    assert {'name': 'loki-data', 'mountPath': '/var/loki'} in loki['singleBinary']['extraVolumeMounts']
    assert loki['chunksCache']['enabled'] is False
    assert loki['resultsCache']['enabled'] is False


def test_e2e_observability_jaeger_uses_memory_without_badger_pvc() -> None:
    e2e_values = (ROOT / 'deploy/helm/observability/values-e2e.yaml').read_text()
    values = _load_yaml('deploy/helm/observability/values-e2e.yaml')
    jaeger = values['jaeger']

    assert jaeger['storage']['type'] == 'memory'
    assert jaeger['storage']['badger']['ephemeral'] is True
    assert jaeger['persistence']['enabled'] is False
    assert 'SPAN_STORAGE_TYPE' not in e2e_values


def test_e2e_observability_promtail_uses_kind_host_log_permissions() -> None:
    values = (ROOT / 'deploy/helm/observability/values.yaml').read_text()
    e2e_values = (ROOT / 'deploy/helm/observability/values-e2e.yaml').read_text()
    e2e_values_dict = _load_yaml('deploy/helm/observability/values-e2e.yaml')
    promtail_section = e2e_values.split('\npromtail:\n', 1)[1]
    readiness_probe = e2e_values_dict['promtail']['readinessProbe']

    assert 'extraScrapeConfigs' not in values
    assert readiness_probe['httpGet']['path'] == '/metrics'
    assert readiness_probe['httpGet']['port'] == 'http-metrics'
    assert 'runAsNonRoot: false' in promtail_section
    assert 'runAsUser: 0' in promtail_section
    assert 'runAsGroup: 0' in promtail_section
    assert 'fsGroup: 0' in promtail_section


def test_e2e_observability_uses_pullable_prometheus_operator_webhook_patch_image() -> None:
    values = _load_yaml('deploy/helm/observability/values-e2e.yaml')
    patch_image = values['kube-prometheus-stack']['prometheusOperator']['admissionWebhooks']['patch']['image']

    assert patch_image['registry'] == 'registry.k8s.io'
    assert patch_image['repository'] == 'ingress-nginx/kube-webhook-certgen'
    assert patch_image['tag'] == 'v1.5.3'
    assert patch_image['sha'] == ''


def test_makefile_renders_cluster_specific_kind_config() -> None:
    makefile = (ROOT / 'tests/e2e/Makefile').read_text()
    assert 'render-kind-config' in makefile
    assert 'envsubst < $(KIND_CONFIG_TEMPLATE) > $(KIND_CONFIG_RENDERED)' in makefile
    assert 'PLATFORM_API_URL ?= http://localhost:$(PORT_API)' in makefile
    assert 'PLATFORM_WS_URL ?= ws://localhost:$(PORT_WS)' in makefile


def test_load_images_uses_repo_root_context_for_ui_build() -> None:
    load_images = (ROOT / 'tests/e2e/cluster/load-images.sh').read_text()
    assert 'ghcr.io/musematic/ui:local|apps/web/Dockerfile|.' in load_images
    assert 'local context_path="${ROOT_DIR}/${context}"' in load_images
    assert 'docker buildx build \\' in load_images
    assert 'DOCKER_BUILDKIT=1 docker build --rm --force-rm -t "${image}" -f "${dockerfile_path}" "${context_path}"' in load_images


def test_cluster_scripts_have_valid_bash_shebangs() -> None:
    install_bytes = (ROOT / 'tests/e2e/cluster/install.sh').read_bytes()
    load_bytes = (ROOT / 'tests/e2e/cluster/load-images.sh').read_bytes()
    capture_bytes = (ROOT / 'tests/e2e/cluster/capture-state.sh').read_bytes()
    assert install_bytes.startswith(b'#!/usr/bin/env bash\n')
    assert load_bytes.startswith(b'#!/usr/bin/env bash\n')
    assert capture_bytes.startswith(b'#!/usr/bin/env bash\n')


def test_e2e_values_disable_blocking_helm_hook_jobs() -> None:
    values = (ROOT / 'tests/e2e/cluster/values-e2e.yaml').read_text()
    neo4j_section = values.split('\nclickhouse:\n', 1)[0].split('\nneo4j:\n', 1)[1]
    clickhouse_section = values.split('\nopensearch:\n', 1)[0].split('\nclickhouse:\n', 1)[1]

    assert "migration:\n    enabled: false" in values
    assert "bucketInit:\n    enabled: false" in values
    assert values.count("schemaInit:\n    enabled: false") == 2
    assert "  backup:\n    enabled: false" in neo4j_section
    assert "  schemaInit:\n    enabled: false" in neo4j_section
    assert "  schemaInit:\n    enabled: false" in clickhouse_section


def test_install_script_uses_extended_helm_timeout() -> None:
    install_script = (ROOT / 'tests/e2e/cluster/install.sh').read_text()
    assert 'HELM_TIMEOUT="${HELM_TIMEOUT:-20m}"' in install_script
    assert '--timeout "${HELM_TIMEOUT}"' in install_script


def test_install_script_runs_manual_init_jobs_and_ignores_completed_pods() -> None:
    install_script = (ROOT / 'tests/e2e/cluster/install.sh').read_text()
    assert 'run_manual_init_jobs' in install_script
    assert 'launch_minio_bucket_init' in install_script
    assert 'launch_clickhouse_schema_init' in install_script
    assert 'launch_neo4j_schema_init' in install_script
    assert 'launch_control_plane_migration' in install_script
    assert 'wait_for_job_completion' in install_script
    assert '--field-selector=status.phase!=Succeeded' in install_script
    assert 'kubectl rollout restart -n "${NAMESPACE}" "$deployment"' in install_script


def test_install_script_prints_kafka_diagnostics_on_readiness_timeout() -> None:
    install_script = (ROOT / 'tests/e2e/cluster/install.sh').read_text()

    assert 'Kafka cluster ${KAFKA_CLUSTER_NAME} did not become Ready' in install_script
    assert 'kubectl get kafka -n "${KAFKA_NAMESPACE}" "${KAFKA_CLUSTER_NAME}" -o yaml' in install_script
    assert 'kubectl describe pods -n "${KAFKA_NAMESPACE}" -l "strimzi.io/cluster=${KAFKA_CLUSTER_NAME}"' in install_script


def test_platform_chart_creates_platform_data_namespace_once() -> None:
    template = (ROOT / 'deploy/helm/platform/templates/platform-data-namespace.yaml').read_text()
    values = _load_yaml('deploy/helm/platform/values.yaml')
    assert 'kind: Namespace' in template
    assert values['platformDataNamespace']['name'] == 'platform-data'

    data_subcharts = [
        'postgresql',
        'redis',
        'minio',
        'qdrant',
        'neo4j',
        'clickhouse',
    ]
    for subchart in data_subcharts:
        assert values[subchart]['enabled'] is True
        assert values[subchart]['createNamespace'] is False


def test_data_subcharts_gate_namespace_creation_and_kafka_listener_uses_valid_port() -> None:
    namespace_templates = [
        ROOT / 'deploy/helm/postgresql/templates/namespace.yaml',
        ROOT / 'deploy/helm/redis/templates/namespace.yaml',
        ROOT / 'deploy/helm/minio/templates/namespace.yaml',
        ROOT / 'deploy/helm/qdrant/templates/namespace.yaml',
        ROOT / 'deploy/helm/neo4j/templates/namespace.yaml',
        ROOT / 'deploy/helm/clickhouse/templates/namespace.yaml',
    ]
    for template in namespace_templates:
        contents = template.read_text()
        assert 'createNamespace' in contents

    kafka_template = (ROOT / 'deploy/helm/kafka/templates/kafka.yaml').read_text()
    kafka_network_policy = (ROOT / 'deploy/helm/kafka/templates/network-policy.yaml').read_text()
    kafka_combined_pool = (ROOT / 'deploy/helm/kafka/templates/kafka-node-pool-combined.yaml').read_text()
    assert 'port: 9093' in kafka_template
    assert 'port: 9091' not in kafka_template
    assert 'port: 9093' in kafka_network_policy
    assert 'port: 9091' not in kafka_network_policy
    assert '{{- with .Values.jvmOptions }}' in kafka_combined_pool
    assert '{{- with .Values.resources }}' in kafka_combined_pool


def test_e2e_kafka_uses_kind_sized_node_pool_resources() -> None:
    values = _load_yaml('tests/e2e/cluster/values-e2e.yaml')
    kafka = values['kafka']

    assert kafka['combined'] is True
    assert kafka['jvmOptions']['-Xms'] == '256m'
    assert kafka['jvmOptions']['-Xmx'] == '512m'
    assert kafka['resources']['requests'] == {'cpu': '100m', 'memory': '512Mi'}
    assert kafka['resources']['limits'] == {'cpu': '500m', 'memory': '1Gi'}


def test_cnpg_templates_use_current_monitoring_and_postgresql_fields() -> None:
    cluster_template = (ROOT / 'deploy/helm/postgresql/templates/cluster.yaml').read_text()
    pooler_template = (ROOT / 'deploy/helm/postgresql/templates/pooler.yaml').read_text()

    assert 'enablePodMonitor' in cluster_template
    assert 'monitoring:\n    enabled:' not in cluster_template
    assert 'postgresql:\n    version:' not in cluster_template
    assert 'enablePodMonitor' in pooler_template
    assert 'monitoring:\n    enabled:' not in pooler_template


def test_install_script_parses_kind_version_with_backreference() -> None:
    install_script = (ROOT / 'tests/e2e/cluster/install.sh').read_text()
    assert "sed -E 's/.*v([0-9]+\\.[0-9]+\\.[0-9]+).*/\\1/'" in install_script


def test_load_images_prunes_docker_cache_between_images() -> None:
    load_images = (ROOT / 'tests/e2e/cluster/load-images.sh').read_text()
    assert 'docker build --rm --force-rm' in load_images
    assert 'docker image rm -f "${image}"' in load_images
    assert 'docker image prune -af' in load_images
    assert 'docker builder prune -af' in load_images


def test_minio_bucket_init_can_be_disabled_without_losing_the_configmap() -> None:
    values = (ROOT / 'deploy/helm/minio/values.yaml').read_text()
    regular_job = (ROOT / 'deploy/helm/minio/templates/bucket-init-job.yaml').read_text()
    generic_job = (ROOT / 'deploy/helm/minio/templates/bucket-init-job-generic.yaml').read_text()
    configmap = (ROOT / 'deploy/helm/minio/templates/bucket-init-configmap.yaml').read_text()

    assert 'bucketInit:' in values
    assert '{{- if and .Values.minio.enabled .Values.bucketInit.enabled }}' in regular_job
    assert '{{- if and (not .Values.minio.enabled) .Values.bucketInit.enabled }}' in generic_job
    assert '{{- if .Values.minio.enabled }}' in configmap


def test_capture_state_collects_jobs_and_descriptions() -> None:
    script = (ROOT / 'tests/e2e/cluster/capture-state.sh').read_text()
    assert 'kubectl get jobs -A' in script
    assert 'kubectl describe jobs -A' in script
    assert 'kubectl describe -n "${namespace}" "${pod}"' in script
    assert 'strimzi-system' in script


def test_e2e_workflow_frees_runner_disk_before_bootstrap() -> None:
    workflow = (ROOT / '.github/workflows/e2e.yml').read_text()
    assert 'Free runner disk space' in workflow
    assert 'docker system prune -af --volumes || true' in workflow
    assert 'rm -rf /usr/local/lib/android' in workflow
    assert 'rm -rf /usr/share/dotnet' in workflow
    assert 'rm -rf /usr/share/swift' in workflow
    assert 'rm -rf /opt/ghc' in workflow
    assert 'rm -rf /opt/hostedtoolcache/CodeQL' in workflow


def test_e2e_test_target_uses_versioned_test_paths() -> None:
    makefile = (ROOT / 'tests/e2e/Makefile').read_text()
    assert 'E2E_TEST_PATHS ?= suites' in makefile
    assert '$(PYTEST) $(E2E_TEST_PATHS)' in makefile
    assert '$(PYTEST) suites' not in makefile
