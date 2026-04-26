from __future__ import annotations

# ruff: noqa: E501
from typing import Any

from sqlalchemy import Table, column, literal_column, table
from sqlalchemy.dialects.postgresql import insert

RUNBOOKS_V1: tuple[dict[str, Any], ...] = (
    {
        "scenario": "pod_failure",
        "title": "Pod Failure",
        "symptoms": "One or more platform pods are not Ready, have high restart counts, or are missing from their expected deployment.",
        "diagnostic_commands": [
            {
                "command": "kubectl get pods -A --field-selector=status.phase!=Running",
                "description": "List pods outside the normal running state.",
            },
            {
                "command": "kubectl describe pod <pod> -n <namespace>",
                "description": "Inspect scheduling, image, probe, and event details.",
            },
        ],
        "remediation_steps": "Confirm whether the failure is isolated, check recent deploys, inspect events, restart only the affected workload if the failure is transient, and roll back the owning deployment if the new revision caused the failure.",
        "escalation_path": "Escalate to the platform runtime owner if more than one namespace is affected or the pod belongs to a shared control-plane service.",
    },
    {
        "scenario": "database_connection_issue",
        "title": "Database Connection Issue",
        "symptoms": "API requests fail with database connection errors, pool exhaustion, or elevated query latency.",
        "diagnostic_commands": [
            {
                "command": "kubectl -n platform-data get cluster postgresql",
                "description": "Check CloudNativePG cluster health.",
            },
            {
                "command": "kubectl -n platform-data logs deploy/postgresql-pooler --tail=200",
                "description": "Inspect pooler connection churn and authentication errors.",
            },
        ],
        "remediation_steps": "Validate database pods are healthy, check pool saturation, reduce noisy worker concurrency if needed, and fail over only after confirming primary unavailability.",
        "escalation_path": "Escalate to database operations for persistent replication lag, failed failover, or storage pressure.",
    },
    {
        "scenario": "kafka_lag",
        "title": "Kafka Lag",
        "symptoms": "Consumers fall behind expected offsets, event processing latency increases, or DLQ volume rises.",
        "diagnostic_commands": [
            {
                "command": "kubectl -n platform-data exec -it kafka-cluster-kafka-0 -- bin/kafka-consumer-groups.sh --bootstrap-server kafka-cluster-kafka-bootstrap:9092 --describe --all-groups",
                "description": "Inspect consumer lag by group and topic.",
            },
            {
                "command": "kubectl -n platform-data get kafkatopic",
                "description": "Verify managed topics and partition counts.",
            },
        ],
        "remediation_steps": "Identify the lagging consumer group, check consumer errors, scale the owning worker if partitions permit, and pause low-priority producers if broker pressure is broad.",
        "escalation_path": "Escalate to event-platform owners if broker disk, ISR, or controller instability is present.",
    },
    {
        "scenario": "model_provider_outage",
        "title": "Model Provider Outage",
        "symptoms": "Model router calls time out, fallback rate rises, or a provider reports 5xx/429 responses.",
        "diagnostic_commands": [
            {
                "command": "kubectl -n platform logs deploy/control-plane --tail=200 | grep model_router",
                "description": "Inspect model-router provider failures and fallback decisions.",
            },
            {
                "command": "kubectl -n platform get configmap model-catalog -o yaml",
                "description": "Review active provider bindings and fallback policy.",
            },
        ],
        "remediation_steps": "Verify provider status, confirm credentials resolve through the secret provider, route traffic to configured fallbacks, and reduce non-critical batch work until recovery.",
        "escalation_path": "Escalate to the AI platform owner if all configured providers are unavailable or catalog policy blocks fallback.",
    },
    {
        "scenario": "certificate_expiry",
        "title": "Certificate Expiry",
        "symptoms": "TLS handshakes fail, cert-manager reports renewal errors, or gateway certificates are near expiry.",
        "diagnostic_commands": [
            {
                "command": "kubectl -n platform get certificate,challenge,order",
                "description": "Check cert-manager renewal state.",
            },
            {
                "command": "kubectl -n platform get secret gateway-tls -o jsonpath='{.data.tls\\.crt}' | base64 -d | openssl x509 -noout -dates",
                "description": "Inspect the gateway certificate validity window.",
            },
        ],
        "remediation_steps": "Check issuer health, DNS/HTTP challenge reachability, renew the certificate after fixing issuer errors, and reload gateway pods only after the secret updates.",
        "escalation_path": "Escalate to infrastructure security if issuer credentials or CA policy blocks renewal.",
    },
    {
        "scenario": "s3_quota_breach",
        "title": "S3 Quota Breach",
        "symptoms": "Object uploads fail, evidence or artifact writes return quota errors, or bucket usage grows unexpectedly.",
        "diagnostic_commands": [
            {
                "command": "kubectl -n platform-data exec deploy/minio-client -- mc du --recursive platform",
                "description": "Review bucket usage by prefix.",
            },
            {
                "command": "kubectl -n platform logs deploy/control-plane --tail=200 | grep ObjectStorageError",
                "description": "Find object-storage write failures.",
            },
        ],
        "remediation_steps": "Identify the largest prefix, expire safe temporary objects, verify lifecycle policies, and increase quota only after confirming growth is expected.",
        "escalation_path": "Escalate to storage operations for tenant-wide capacity pressure or failed lifecycle cleanup.",
    },
    {
        "scenario": "governance_verdict_storm",
        "title": "Governance Verdict Storm",
        "symptoms": "A sudden spike of governance verdicts or enforcement events blocks workflows across multiple workspaces.",
        "diagnostic_commands": [
            {
                "command": "kubectl -n platform logs deploy/control-plane --tail=300 | grep governance",
                "description": "Inspect recent governance verdict and enforcement logs.",
            },
            {
                "command": "kubectl -n platform-data exec -it kafka-cluster-kafka-0 -- bin/kafka-console-consumer.sh --bootstrap-server kafka-cluster-kafka-bootstrap:9092 --topic governance.verdict.issued --from-beginning --max-messages 20",
                "description": "Sample recent verdict events.",
            },
        ],
        "remediation_steps": "Confirm whether a policy release caused the storm, pause the affected policy revision if needed, and verify enforcement backlogs drain.",
        "escalation_path": "Escalate to governance owners when a policy rollback is required or customer workloads are broadly blocked.",
    },
    {
        "scenario": "auth_service_degradation",
        "title": "Auth Service Degradation",
        "symptoms": "Login, token refresh, OAuth callback, or permission checks degrade or fail.",
        "diagnostic_commands": [
            {
                "command": "kubectl -n platform logs deploy/control-plane --tail=200 | grep -E 'auth|oauth|permission'",
                "description": "Inspect auth and authorization failures.",
            },
            {
                "command": "kubectl -n platform get secret auth-signing-keys -o yaml",
                "description": "Confirm signing key secret presence without printing secret values.",
            },
        ],
        "remediation_steps": "Check signing-key availability, OAuth provider health, Redis session health, and database latency before restarting auth-serving pods.",
        "escalation_path": "Escalate to identity operations for provider-side outage or suspected credential compromise.",
    },
    {
        "scenario": "reasoning_engine_oom",
        "title": "Reasoning Engine OOM",
        "symptoms": "Reasoning engine pods restart with OOMKilled, active reasoning traces abort, or memory alerts fire.",
        "diagnostic_commands": [
            {
                "command": "kubectl -n platform describe pod -l app.kubernetes.io/name=reasoning-engine",
                "description": "Check restart reason and resource limits.",
            },
            {
                "command": "kubectl -n platform top pod -l app.kubernetes.io/name=reasoning-engine",
                "description": "Review current memory pressure.",
            },
        ],
        "remediation_steps": "Reduce concurrency, inspect recent request mix, increase memory limits only after verifying no leak, and drain workloads before rolling the deployment.",
        "escalation_path": "Escalate to reasoning-engine owners for repeated OOMs or trace corruption.",
    },
    {
        "scenario": "runtime_pod_crash_loop",
        "title": "Runtime Pod Crash Loop",
        "symptoms": "Runtime-controller or execution runtime pods enter CrashLoopBackOff and workflow dispatch stalls.",
        "diagnostic_commands": [
            {
                "command": "kubectl -n platform get pods -l app.kubernetes.io/name=runtime-controller",
                "description": "Find crash-looping runtime-controller pods.",
            },
            {
                "command": "kubectl -n platform logs deploy/runtime-controller --previous --tail=200",
                "description": "Read the previous container logs for crash cause.",
            },
        ],
        "remediation_steps": "Check image rollout, configuration secret availability, and runtime-controller dependencies; roll back the deployment when the crash correlates with a new revision.",
        "escalation_path": "Escalate to runtime owners if workflow execution is globally blocked or crash loops persist after rollback.",
    },
)

RUNBOOK_SCENARIOS: tuple[str, ...] = tuple(row["scenario"] for row in RUNBOOKS_V1)


def _runbooks_table() -> Table:
    return table(
        "runbooks",
        column("scenario"),
        column("title"),
        column("symptoms"),
        column("diagnostic_commands"),
        column("remediation_steps"),
        column("escalation_path"),
        column("status"),
    )


def seed_initial_runbooks(connection: Any) -> None:
    statement = insert(_runbooks_table()).values(
        [
            {
                **row,
                "status": "active",
            }
            for row in RUNBOOKS_V1
        ]
    )
    statement = statement.on_conflict_do_nothing(index_elements=[literal_column("scenario")])
    connection.execute(statement)
