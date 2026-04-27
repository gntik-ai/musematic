# simulation-controller

![Version: 0.1.0](https://img.shields.io/badge/Version-0.1.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 0.1.0](https://img.shields.io/badge/AppVersion-0.1.0-informational?style=flat-square)

Helm chart for the Musematic simulation controller

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| env | object | `{"DEFAULT_MAX_DURATION_SECONDS":"3600","GRPC_PORT":"50055","ORPHAN_SCAN_INTERVAL_SECONDS":"60","OTEL_EXPORTER_OTLP_ENDPOINT":"http://otel-collector.platform-observability.svc.cluster.local:4317","OTEL_RESOURCE_ATTRIBUTES":"deployment.environment=production","OTEL_SERVICE_NAME":"simulation-controller","SIMULATION_BUCKET":"simulation-artifacts","SIMULATION_NAMESPACE":"platform-simulation"}` | Configures `env` for the simulation-controller chart. |
| env.DEFAULT_MAX_DURATION_SECONDS | string | `"3600"` | Configures `env.DEFAULT_MAX_DURATION_SECONDS` for the simulation-controller chart. |
| env.GRPC_PORT | string | `"50055"` | Configures `env.GRPC_PORT` for the simulation-controller chart. |
| env.ORPHAN_SCAN_INTERVAL_SECONDS | string | `"60"` | Configures `env.ORPHAN_SCAN_INTERVAL_SECONDS` for the simulation-controller chart. |
| env.OTEL_EXPORTER_OTLP_ENDPOINT | string | `"http://otel-collector.platform-observability.svc.cluster.local:4317"` | Configures `env.OTEL_EXPORTER_OTLP_ENDPOINT` for the simulation-controller chart. |
| env.OTEL_RESOURCE_ATTRIBUTES | string | `"deployment.environment=production"` | Configures `env.OTEL_RESOURCE_ATTRIBUTES` for the simulation-controller chart. |
| env.OTEL_SERVICE_NAME | string | `"simulation-controller"` | Configures `env.OTEL_SERVICE_NAME` for the simulation-controller chart. |
| env.SIMULATION_BUCKET | string | `"simulation-artifacts"` | Configures `env.SIMULATION_BUCKET` for the simulation-controller chart. |
| env.SIMULATION_NAMESPACE | string | `"platform-simulation"` | Configures `env.SIMULATION_NAMESPACE` for the simulation-controller chart. |
| image | object | `{"pullPolicy":"IfNotPresent","repository":"musematic/simulation-controller","tag":"latest"}` | Configures `image` for the simulation-controller chart. |
| image.pullPolicy | string | `"IfNotPresent"` | Configures `image.pullPolicy` for the simulation-controller chart. |
| image.repository | string | `"musematic/simulation-controller"` | Configures `image.repository` for the simulation-controller chart. |
| image.tag | string | `"latest"` | Configures `image.tag` for the simulation-controller chart. |
| replicaCount | int | `1` | Configures `replicaCount` for the simulation-controller chart. |
| resources | object | `{"limits":{"cpu":"500m","memory":"256Mi"},"requests":{"cpu":"250m","memory":"128Mi"}}` | Configures `resources` for the simulation-controller chart. |
| resources.limits | object | `{"cpu":"500m","memory":"256Mi"}` | Configures `resources.limits` for the simulation-controller chart. |
| resources.limits.cpu | string | `"500m"` | Configures `resources.limits.cpu` for the simulation-controller chart. |
| resources.limits.memory | string | `"256Mi"` | Configures `resources.limits.memory` for the simulation-controller chart. |
| resources.requests | object | `{"cpu":"250m","memory":"128Mi"}` | Configures `resources.requests` for the simulation-controller chart. |
| resources.requests.cpu | string | `"250m"` | Configures `resources.requests.cpu` for the simulation-controller chart. |
| resources.requests.memory | string | `"128Mi"` | Configures `resources.requests.memory` for the simulation-controller chart. |
| secrets | object | `{"KAFKA_BROKERS":"","POSTGRES_DSN":"","S3_ACCESS_KEY":"minioadmin","S3_ENDPOINT_URL":"","S3_SECRET_KEY":"minioadmin"}` | Configures `secrets` for the simulation-controller chart. |
| secrets.KAFKA_BROKERS | string | `""` | Configures `secrets.KAFKA_BROKERS` for the simulation-controller chart. |
| secrets.POSTGRES_DSN | string | `""` | Configures `secrets.POSTGRES_DSN` for the simulation-controller chart. |
| secrets.S3_ACCESS_KEY | string | `"minioadmin"` | Configures `secrets.S3_ACCESS_KEY` for the simulation-controller chart. |
| secrets.S3_ENDPOINT_URL | string | `""` | Configures `secrets.S3_ENDPOINT_URL` for the simulation-controller chart. |
| secrets.S3_SECRET_KEY | string | `"minioadmin"` | Configures `secrets.S3_SECRET_KEY` for the simulation-controller chart. |
| service | object | `{"port":50055,"type":"ClusterIP"}` | Configures `service` for the simulation-controller chart. |
| service.port | int | `50055` | Configures `service.port` for the simulation-controller chart. |
| service.type | string | `"ClusterIP"` | Configures `service.type` for the simulation-controller chart. |
| serviceAccount | object | `{"create":true,"name":""}` | Configures `serviceAccount` for the simulation-controller chart. |
| serviceAccount.create | bool | `true` | Configures `serviceAccount.create` for the simulation-controller chart. |
| serviceAccount.name | string | `""` | Configures `serviceAccount.name` for the simulation-controller chart. |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.13.1](https://github.com/norwoodj/helm-docs/releases/v1.13.1)
