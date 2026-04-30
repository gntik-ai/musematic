# reasoning-engine

![Version: 0.1.0](https://img.shields.io/badge/Version-0.1.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 0.1.0](https://img.shields.io/badge/AppVersion-0.1.0-informational?style=flat-square)

Reasoning engine satellite service for Musematic.

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| config | object | `{"budgetDefaultTTLSeconds":"3600","maxTotConcurrency":"10","otelExporterOtlpEndpoint":"http://otel-collector.platform-observability.svc.cluster.local:4317","otelResourceAttributes":"deployment.environment=production","otelServiceName":"reasoning-engine","startupDependencyRetryIntervalSeconds":"5","startupDependencyTimeoutSeconds":"600","traceBufferSize":"10000","tracePayloadThreshold":"65536"}` | Configures `config` for the reasoning-engine chart. |
| config.budgetDefaultTTLSeconds | string | `"3600"` | Configures `config.budgetDefaultTTLSeconds` for the reasoning-engine chart. |
| config.maxTotConcurrency | string | `"10"` | Configures `config.maxTotConcurrency` for the reasoning-engine chart. |
| config.otelExporterOtlpEndpoint | string | `"http://otel-collector.platform-observability.svc.cluster.local:4317"` | Configures `config.otelExporterOtlpEndpoint` for the reasoning-engine chart. |
| config.otelResourceAttributes | string | `"deployment.environment=production"` | Configures `config.otelResourceAttributes` for the reasoning-engine chart. |
| config.otelServiceName | string | `"reasoning-engine"` | Configures `config.otelServiceName` for the reasoning-engine chart. |
| config.startupDependencyRetryIntervalSeconds | string | `"5"` | Configures `config.startupDependencyRetryIntervalSeconds` for the reasoning-engine chart. |
| config.startupDependencyTimeoutSeconds | string | `"600"` | Configures `config.startupDependencyTimeoutSeconds` for the reasoning-engine chart. |
| config.traceBufferSize | string | `"10000"` | Configures `config.traceBufferSize` for the reasoning-engine chart. |
| config.tracePayloadThreshold | string | `"65536"` | Configures `config.tracePayloadThreshold` for the reasoning-engine chart. |
| configSecretRef | string | `"reasoning-engine-config"` | Configures `configSecretRef` for the reasoning-engine chart. |
| grpcPort | int | `50052` | Configures `grpcPort` for the reasoning-engine chart. |
| hpa | object | `{"maxReplicas":10,"minReplicas":2,"targetCPUUtilizationPercentage":70}` | Configures `hpa` for the reasoning-engine chart. |
| hpa.maxReplicas | int | `10` | Configures `hpa.maxReplicas` for the reasoning-engine chart. |
| hpa.minReplicas | int | `2` | Configures `hpa.minReplicas` for the reasoning-engine chart. |
| hpa.targetCPUUtilizationPercentage | int | `70` | Configures `hpa.targetCPUUtilizationPercentage` for the reasoning-engine chart. |
| image | object | `{"pullPolicy":"IfNotPresent","repository":"ghcr.io/andrea-mucci/musematic/reasoning-engine","tag":"latest"}` | Configures `image` for the reasoning-engine chart. |
| image.pullPolicy | string | `"IfNotPresent"` | Configures `image.pullPolicy` for the reasoning-engine chart. |
| image.repository | string | `"ghcr.io/andrea-mucci/musematic/reasoning-engine"` | Configures `image.repository` for the reasoning-engine chart. |
| image.tag | string | `"latest"` | Configures `image.tag` for the reasoning-engine chart. |
| probes | object | `{"startup":{"failureThreshold":90,"periodSeconds":10}}` | Configures `probes` for the reasoning-engine chart. |
| probes.startup | object | `{"failureThreshold":90,"periodSeconds":10}` | Configures `probes.startup` for the reasoning-engine chart. |
| probes.startup.failureThreshold | int | `90` | Configures `probes.startup.failureThreshold` for the reasoning-engine chart. |
| probes.startup.periodSeconds | int | `10` | Configures `probes.startup.periodSeconds` for the reasoning-engine chart. |
| replicaCount | int | `2` | Configures `replicaCount` for the reasoning-engine chart. |
| resources | object | `{"limits":{"cpu":"500m","memory":"256Mi"},"requests":{"cpu":"250m","memory":"128Mi"}}` | Configures `resources` for the reasoning-engine chart. |
| resources.limits | object | `{"cpu":"500m","memory":"256Mi"}` | Configures `resources.limits` for the reasoning-engine chart. |
| resources.limits.cpu | string | `"500m"` | Configures `resources.limits.cpu` for the reasoning-engine chart. |
| resources.limits.memory | string | `"256Mi"` | Configures `resources.limits.memory` for the reasoning-engine chart. |
| resources.requests | object | `{"cpu":"250m","memory":"128Mi"}` | Configures `resources.requests` for the reasoning-engine chart. |
| resources.requests.cpu | string | `"250m"` | Configures `resources.requests.cpu` for the reasoning-engine chart. |
| resources.requests.memory | string | `"128Mi"` | Configures `resources.requests.memory` for the reasoning-engine chart. |
| secrets | object | `{"KAFKA_BROKERS":"","MINIO_BUCKET":"reasoning-traces","MINIO_ENDPOINT":"","POSTGRES_DSN":"","REDIS_ADDR":"","REDIS_PASSWORD":""}` | Configures `secrets` for the reasoning-engine chart. |
| secrets.KAFKA_BROKERS | string | `""` | Configures `secrets.KAFKA_BROKERS` for the reasoning-engine chart. |
| secrets.MINIO_BUCKET | string | `"reasoning-traces"` | Configures `secrets.MINIO_BUCKET` for the reasoning-engine chart. |
| secrets.MINIO_ENDPOINT | string | `""` | Configures `secrets.MINIO_ENDPOINT` for the reasoning-engine chart. |
| secrets.POSTGRES_DSN | string | `""` | Configures `secrets.POSTGRES_DSN` for the reasoning-engine chart. |
| secrets.REDIS_ADDR | string | `""` | Configures `secrets.REDIS_ADDR` for the reasoning-engine chart. |
| secrets.REDIS_PASSWORD | string | `""` | Configures `secrets.REDIS_PASSWORD` for the reasoning-engine chart. |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.13.1](https://github.com/norwoodj/helm-docs/releases/v1.13.1)
