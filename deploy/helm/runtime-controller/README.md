# musematic-runtime-controller

![Version: 0.1.0](https://img.shields.io/badge/Version-0.1.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 0.1.0](https://img.shields.io/badge/AppVersion-0.1.0-informational?style=flat-square)

Runtime controller satellite service for Musematic.

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| config | object | `{"agentPackagePresignTTL":"2h","heartbeatCheckInterval":"10s","heartbeatTimeout":"60s","k8sNamespace":"platform-execution","otelExporterOtlpEndpoint":"http://otel-collector.platform-observability.svc.cluster.local:4317","otelResourceAttributes":"deployment.environment=production","otelServiceName":"runtime-controller","reconcileInterval":"30s","stopGracePeriod":"30s","warmPoolIdleTimeout":"5m","warmPoolReplenishInterval":"30s"}` | Configures `config` for the runtime-controller chart. |
| config.agentPackagePresignTTL | string | `"2h"` | Configures `config.agentPackagePresignTTL` for the runtime-controller chart. |
| config.heartbeatCheckInterval | string | `"10s"` | Configures `config.heartbeatCheckInterval` for the runtime-controller chart. |
| config.heartbeatTimeout | string | `"60s"` | Configures `config.heartbeatTimeout` for the runtime-controller chart. |
| config.k8sNamespace | string | `"platform-execution"` | Configures `config.k8sNamespace` for the runtime-controller chart. |
| config.otelExporterOtlpEndpoint | string | `"http://otel-collector.platform-observability.svc.cluster.local:4317"` | Configures `config.otelExporterOtlpEndpoint` for the runtime-controller chart. |
| config.otelResourceAttributes | string | `"deployment.environment=production"` | Configures `config.otelResourceAttributes` for the runtime-controller chart. |
| config.otelServiceName | string | `"runtime-controller"` | Configures `config.otelServiceName` for the runtime-controller chart. |
| config.reconcileInterval | string | `"30s"` | Configures `config.reconcileInterval` for the runtime-controller chart. |
| config.stopGracePeriod | string | `"30s"` | Configures `config.stopGracePeriod` for the runtime-controller chart. |
| config.warmPoolIdleTimeout | string | `"5m"` | Configures `config.warmPoolIdleTimeout` for the runtime-controller chart. |
| config.warmPoolReplenishInterval | string | `"30s"` | Configures `config.warmPoolReplenishInterval` for the runtime-controller chart. |
| configSecretRef | string | `"runtime-controller-config"` | Configures `configSecretRef` for the runtime-controller chart. |
| grpcPort | int | `50051` | Configures `grpcPort` for the runtime-controller chart. |
| httpPort | int | `8080` | Configures `httpPort` for the runtime-controller chart. |
| image | object | `{"pullPolicy":"IfNotPresent","repository":"ghcr.io/andrea-mucci/musematic/runtime-controller","tag":"latest"}` | Configures `image` for the runtime-controller chart. |
| image.pullPolicy | string | `"IfNotPresent"` | Configures `image.pullPolicy` for the runtime-controller chart. |
| image.repository | string | `"ghcr.io/andrea-mucci/musematic/runtime-controller"` | Configures `image.repository` for the runtime-controller chart. |
| image.tag | string | `"latest"` | Configures `image.tag` for the runtime-controller chart. |
| networkPolicy | object | `{"enabled":true}` | Configures `networkPolicy` for the runtime-controller chart. |
| networkPolicy.enabled | bool | `true` | Configures `networkPolicy.enabled` for the runtime-controller chart. |
| replicaCount | int | `1` | Configures `replicaCount` for the runtime-controller chart. |
| resources | object | `{"limits":{"cpu":"1","memory":"512Mi"},"requests":{"cpu":"250m","memory":"256Mi"}}` | Configures `resources` for the runtime-controller chart. |
| resources.limits | object | `{"cpu":"1","memory":"512Mi"}` | Configures `resources.limits` for the runtime-controller chart. |
| resources.limits.cpu | string | `"1"` | Configures `resources.limits.cpu` for the runtime-controller chart. |
| resources.limits.memory | string | `"512Mi"` | Configures `resources.limits.memory` for the runtime-controller chart. |
| resources.requests | object | `{"cpu":"250m","memory":"256Mi"}` | Configures `resources.requests` for the runtime-controller chart. |
| resources.requests.cpu | string | `"250m"` | Configures `resources.requests.cpu` for the runtime-controller chart. |
| resources.requests.memory | string | `"256Mi"` | Configures `resources.requests.memory` for the runtime-controller chart. |
| secrets | object | `{"K8S_DRY_RUN":"false","KAFKA_BROKERS":"","POSTGRES_DSN":"","REDIS_ADDR":"","REDIS_PASSWORD":"","S3_ACCESS_KEY":"","S3_BUCKET":"","S3_ENDPOINT_URL":"","S3_REGION":"us-east-1","S3_SECRET_KEY":"","S3_USE_PATH_STYLE":"true"}` | Configures `secrets` for the runtime-controller chart. |
| secrets.K8S_DRY_RUN | string | `"false"` | Configures `secrets.K8S_DRY_RUN` for the runtime-controller chart. |
| secrets.KAFKA_BROKERS | string | `""` | Configures `secrets.KAFKA_BROKERS` for the runtime-controller chart. |
| secrets.POSTGRES_DSN | string | `""` | Configures `secrets.POSTGRES_DSN` for the runtime-controller chart. |
| secrets.REDIS_ADDR | string | `""` | Configures `secrets.REDIS_ADDR` for the runtime-controller chart. |
| secrets.REDIS_PASSWORD | string | `""` | Configures `secrets.REDIS_PASSWORD` for the runtime-controller chart. |
| secrets.S3_ACCESS_KEY | string | `""` | Configures `secrets.S3_ACCESS_KEY` for the runtime-controller chart. |
| secrets.S3_BUCKET | string | `""` | Configures `secrets.S3_BUCKET` for the runtime-controller chart. |
| secrets.S3_ENDPOINT_URL | string | `""` | Configures `secrets.S3_ENDPOINT_URL` for the runtime-controller chart. |
| secrets.S3_REGION | string | `"us-east-1"` | Configures `secrets.S3_REGION` for the runtime-controller chart. |
| secrets.S3_SECRET_KEY | string | `""` | Configures `secrets.S3_SECRET_KEY` for the runtime-controller chart. |
| secrets.S3_USE_PATH_STYLE | string | `"true"` | Configures `secrets.S3_USE_PATH_STYLE` for the runtime-controller chart. |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.13.1](https://github.com/norwoodj/helm-docs/releases/v1.13.1)
