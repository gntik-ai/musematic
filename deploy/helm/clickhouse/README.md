# musematic-clickhouse

![Version: 0.1.0](https://img.shields.io/badge/Version-0.1.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 24.3](https://img.shields.io/badge/AppVersion-24.3-informational?style=flat-square)

ClickHouse OLAP analytics for Musematic platform.

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backup | object | `{"bucket":"backups","enabled":true,"image":"altinity/clickhouse-backup:2.5","prefix":"clickhouse","schedule":"0 4 * * *"}` | Configures `backup` for the clickhouse chart. |
| backup.bucket | string | `"backups"` | Configures `backup.bucket` for the clickhouse chart. |
| backup.enabled | bool | `true` | Configures `backup.enabled` for the clickhouse chart. |
| backup.image | string | `"altinity/clickhouse-backup:2.5"` | Configures `backup.image` for the clickhouse chart. |
| backup.prefix | string | `"clickhouse"` | Configures `backup.prefix` for the clickhouse chart. |
| backup.schedule | string | `"0 4 * * *"` | Configures `backup.schedule` for the clickhouse chart. |
| clickhouse | object | `{"auth":{"password":"","user":"default"},"clusterName":"musematic-clickhouse","config":{"max_insert_block_size":1048576,"max_memory_usage":"4000000000"},"image":"clickhouse/clickhouse-server:24.3","keeper":{"enabled":true,"image":"clickhouse/clickhouse-keeper:24.3","replicaCount":3},"replicaCount":2,"resources":{"limits":{"cpu":"4","memory":"8Gi"},"requests":{"cpu":"2","memory":"4Gi"}}}` | Configures `clickhouse` for the clickhouse chart. |
| clickhouse.auth | object | `{"password":"","user":"default"}` | Configures `clickhouse.auth` for the clickhouse chart. |
| clickhouse.auth.password | string | `""` | Configures `clickhouse.auth.password` for the clickhouse chart. |
| clickhouse.auth.user | string | `"default"` | Configures `clickhouse.auth.user` for the clickhouse chart. |
| clickhouse.clusterName | string | `"musematic-clickhouse"` | Configures `clickhouse.clusterName` for the clickhouse chart. |
| clickhouse.config | object | `{"max_insert_block_size":1048576,"max_memory_usage":"4000000000"}` | Configures `clickhouse.config` for the clickhouse chart. |
| clickhouse.config.max_insert_block_size | int | `1048576` | Configures `clickhouse.config.max_insert_block_size` for the clickhouse chart. |
| clickhouse.config.max_memory_usage | string | `"4000000000"` | Configures `clickhouse.config.max_memory_usage` for the clickhouse chart. |
| clickhouse.image | string | `"clickhouse/clickhouse-server:24.3"` | Configures `clickhouse.image` for the clickhouse chart. |
| clickhouse.keeper | object | `{"enabled":true,"image":"clickhouse/clickhouse-keeper:24.3","replicaCount":3}` | Configures `clickhouse.keeper` for the clickhouse chart. |
| clickhouse.keeper.enabled | bool | `true` | Configures `clickhouse.keeper.enabled` for the clickhouse chart. |
| clickhouse.keeper.image | string | `"clickhouse/clickhouse-keeper:24.3"` | Configures `clickhouse.keeper.image` for the clickhouse chart. |
| clickhouse.keeper.replicaCount | int | `3` | Configures `clickhouse.keeper.replicaCount` for the clickhouse chart. |
| clickhouse.replicaCount | int | `2` | Configures `clickhouse.replicaCount` for the clickhouse chart. |
| clickhouse.resources | object | `{"limits":{"cpu":"4","memory":"8Gi"},"requests":{"cpu":"2","memory":"4Gi"}}` | Configures `clickhouse.resources` for the clickhouse chart. |
| clickhouse.resources.limits | object | `{"cpu":"4","memory":"8Gi"}` | Configures `clickhouse.resources.limits` for the clickhouse chart. |
| clickhouse.resources.limits.cpu | string | `"4"` | Configures `clickhouse.resources.limits.cpu` for the clickhouse chart. |
| clickhouse.resources.limits.memory | string | `"8Gi"` | Configures `clickhouse.resources.limits.memory` for the clickhouse chart. |
| clickhouse.resources.requests | object | `{"cpu":"2","memory":"4Gi"}` | Configures `clickhouse.resources.requests` for the clickhouse chart. |
| clickhouse.resources.requests.cpu | string | `"2"` | Configures `clickhouse.resources.requests.cpu` for the clickhouse chart. |
| clickhouse.resources.requests.memory | string | `"4Gi"` | Configures `clickhouse.resources.requests.memory` for the clickhouse chart. |
| createNamespace | bool | `true` | Configures `createNamespace` for the clickhouse chart. |
| networkPolicy | object | `{"enabled":true}` | Configures `networkPolicy` for the clickhouse chart. |
| networkPolicy.enabled | bool | `true` | Configures `networkPolicy.enabled` for the clickhouse chart. |
| persistence | object | `{"keeperSize":"5Gi","size":"50Gi","storageClassName":"standard"}` | Configures `persistence` for the clickhouse chart. |
| persistence.keeperSize | string | `"5Gi"` | Configures `persistence.keeperSize` for the clickhouse chart. |
| persistence.size | string | `"50Gi"` | Configures `persistence.size` for the clickhouse chart. |
| persistence.storageClassName | string | `"standard"` | Configures `persistence.storageClassName` for the clickhouse chart. |
| schemaInit | object | `{"enabled":true,"image":"clickhouse/clickhouse-server:24.3","retries":60,"retryIntervalSeconds":5}` | Configures `schemaInit` for the clickhouse chart. |
| schemaInit.enabled | bool | `true` | Configures `schemaInit.enabled` for the clickhouse chart. |
| schemaInit.image | string | `"clickhouse/clickhouse-server:24.3"` | Configures `schemaInit.image` for the clickhouse chart. |
| schemaInit.retries | int | `60` | Configures `schemaInit.retries` for the clickhouse chart. |
| schemaInit.retryIntervalSeconds | int | `5` | Configures `schemaInit.retryIntervalSeconds` for the clickhouse chart. |
| service | object | `{"httpPort":8123,"interserverHttpPort":9009,"nativePort":9000,"type":"ClusterIP"}` | Configures `service` for the clickhouse chart. |
| service.httpPort | int | `8123` | Configures `service.httpPort` for the clickhouse chart. |
| service.interserverHttpPort | int | `9009` | Configures `service.interserverHttpPort` for the clickhouse chart. |
| service.nativePort | int | `9000` | Configures `service.nativePort` for the clickhouse chart. |
| service.type | string | `"ClusterIP"` | Configures `service.type` for the clickhouse chart. |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.13.1](https://github.com/norwoodj/helm-docs/releases/v1.13.1)
