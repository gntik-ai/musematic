# musematic-qdrant

![Version: 0.1.0](https://img.shields.io/badge/Version-0.1.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 1.16.3](https://img.shields.io/badge/AppVersion-1.16.3-informational?style=flat-square)

Qdrant vector search for Musematic platform.

## Requirements

| Repository | Name | Version |
|------------|------|---------|
| https://qdrant.github.io/qdrant-helm | qdrant | 1.16.3 |

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backup | object | `{"bucket":"backups","enabled":true,"image":{"repository":"ghcr.io/gntik-ai/musematic-control-plane","tag":"latest"},"prefix":"qdrant","schedule":"0 2 * * *"}` | Configures `backup` for the qdrant chart. |
| backup.bucket | string | `"backups"` | Configures `backup.bucket` for the qdrant chart. |
| backup.enabled | bool | `true` | Configures `backup.enabled` for the qdrant chart. |
| backup.image | object | `{"repository":"ghcr.io/gntik-ai/musematic-control-plane","tag":"latest"}` | Configures `backup.image` for the qdrant chart. |
| backup.image.repository | string | `"ghcr.io/gntik-ai/musematic-control-plane"` | Configures `backup.image.repository` for the qdrant chart. |
| backup.image.tag | string | `"latest"` | Configures `backup.image.tag` for the qdrant chart. |
| backup.prefix | string | `"qdrant"` | Configures `backup.prefix` for the qdrant chart. |
| backup.schedule | string | `"0 2 * * *"` | Configures `backup.schedule` for the qdrant chart. |
| collections | object | `{"dimensions":768,"replicationFactor":2}` | Configures `collections` for the qdrant chart. |
| collections.dimensions | int | `768` | Configures `collections.dimensions` for the qdrant chart. |
| collections.replicationFactor | int | `2` | Configures `collections.replicationFactor` for the qdrant chart. |
| createNamespace | bool | `true` | Configures `createNamespace` for the qdrant chart. |
| networkPolicy | object | `{"enabled":true}` | Configures `networkPolicy` for the qdrant chart. |
| networkPolicy.enabled | bool | `true` | Configures `networkPolicy.enabled` for the qdrant chart. |
| qdrant | object | `{"config":{"cluster":{"enabled":true,"p2p":{"port":6335}},"storage":{"hnsw_index":{"ef_construct":128,"m":16}}},"env":[{"name":"QDRANT__SERVICE__API_KEY","valueFrom":{"secretKeyRef":{"key":"QDRANT_API_KEY","name":"qdrant-api-key"}}}],"persistence":{"size":"50Gi","storageClassName":"standard"},"replicaCount":3,"resources":{"requests":{"cpu":"1","memory":"2Gi"}}}` | Configures `qdrant` for the qdrant chart. |
| qdrant.config | object | `{"cluster":{"enabled":true,"p2p":{"port":6335}},"storage":{"hnsw_index":{"ef_construct":128,"m":16}}}` | Configures `qdrant.config` for the qdrant chart. |
| qdrant.config.cluster | object | `{"enabled":true,"p2p":{"port":6335}}` | Configures `qdrant.config.cluster` for the qdrant chart. |
| qdrant.config.cluster.enabled | bool | `true` | Configures `qdrant.config.cluster.enabled` for the qdrant chart. |
| qdrant.config.cluster.p2p | object | `{"port":6335}` | Configures `qdrant.config.cluster.p2p` for the qdrant chart. |
| qdrant.config.cluster.p2p.port | int | `6335` | Configures `qdrant.config.cluster.p2p.port` for the qdrant chart. |
| qdrant.config.storage | object | `{"hnsw_index":{"ef_construct":128,"m":16}}` | Configures `qdrant.config.storage` for the qdrant chart. |
| qdrant.config.storage.hnsw_index | object | `{"ef_construct":128,"m":16}` | Configures `qdrant.config.storage.hnsw_index` for the qdrant chart. |
| qdrant.config.storage.hnsw_index.ef_construct | int | `128` | Configures `qdrant.config.storage.hnsw_index.ef_construct` for the qdrant chart. |
| qdrant.config.storage.hnsw_index.m | int | `16` | Configures `qdrant.config.storage.hnsw_index.m` for the qdrant chart. |
| qdrant.env | list | `[{"name":"QDRANT__SERVICE__API_KEY","valueFrom":{"secretKeyRef":{"key":"QDRANT_API_KEY","name":"qdrant-api-key"}}}]` | Configures `qdrant.env` for the qdrant chart. |
| qdrant.env[0].valueFrom | object | `{"secretKeyRef":{"key":"QDRANT_API_KEY","name":"qdrant-api-key"}}` | Configures `qdrant.env.valueFrom` for the qdrant chart. |
| qdrant.env[0].valueFrom.secretKeyRef | object | `{"key":"QDRANT_API_KEY","name":"qdrant-api-key"}` | Configures `qdrant.env.valueFrom.secretKeyRef` for the qdrant chart. |
| qdrant.env[0].valueFrom.secretKeyRef.key | string | `"QDRANT_API_KEY"` | Configures `qdrant.env.valueFrom.secretKeyRef.key` for the qdrant chart. |
| qdrant.env[0].valueFrom.secretKeyRef.name | string | `"qdrant-api-key"` | Configures `qdrant.env.valueFrom.secretKeyRef.name` for the qdrant chart. |
| qdrant.persistence | object | `{"size":"50Gi","storageClassName":"standard"}` | Configures `qdrant.persistence` for the qdrant chart. |
| qdrant.persistence.size | string | `"50Gi"` | Configures `qdrant.persistence.size` for the qdrant chart. |
| qdrant.persistence.storageClassName | string | `"standard"` | Configures `qdrant.persistence.storageClassName` for the qdrant chart. |
| qdrant.replicaCount | int | `3` | Configures `qdrant.replicaCount` for the qdrant chart. |
| qdrant.resources | object | `{"requests":{"cpu":"1","memory":"2Gi"}}` | Configures `qdrant.resources` for the qdrant chart. |
| qdrant.resources.requests | object | `{"cpu":"1","memory":"2Gi"}` | Configures `qdrant.resources.requests` for the qdrant chart. |
| qdrant.resources.requests.cpu | string | `"1"` | Configures `qdrant.resources.requests.cpu` for the qdrant chart. |
| qdrant.resources.requests.memory | string | `"2Gi"` | Configures `qdrant.resources.requests.memory` for the qdrant chart. |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.13.1](https://github.com/norwoodj/helm-docs/releases/v1.13.1)
