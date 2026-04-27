# musematic-neo4j

![Version: 0.1.0](https://img.shields.io/badge/Version-0.1.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 5.21.2](https://img.shields.io/badge/AppVersion-5.21.2-informational?style=flat-square)

Neo4j graph database for Musematic platform.

## Requirements

| Repository | Name | Version |
|------------|------|---------|
| https://helm.neo4j.com/neo4j | neo4j | 5.21.0 |

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backup | object | `{"bucket":"backups","dataClaimName":"","enabled":true,"image":"neo4j:5.21.2-enterprise","prefix":"neo4j","schedule":"0 3 * * *"}` | Configures `backup` for the neo4j chart. |
| backup.bucket | string | `"backups"` | Configures `backup.bucket` for the neo4j chart. |
| backup.dataClaimName | string | `""` | Configures `backup.dataClaimName` for the neo4j chart. |
| backup.enabled | bool | `true` | Configures `backup.enabled` for the neo4j chart. |
| backup.image | string | `"neo4j:5.21.2-enterprise"` | Configures `backup.image` for the neo4j chart. |
| backup.prefix | string | `"neo4j"` | Configures `backup.prefix` for the neo4j chart. |
| backup.schedule | string | `"0 3 * * *"` | Configures `backup.schedule` for the neo4j chart. |
| createNamespace | bool | `true` | Configures `createNamespace` for the neo4j chart. |
| neo4j | object | `{"acceptLicenseAgreement":"yes","config":{"dbms.security.procedures.allowlist":"apoc.*","dbms.security.procedures.unrestricted":"apoc.*","server.memory.heap.initial_size":"1G","server.memory.heap.max_size":"2G","server.memory.pagecache.size":"1G"},"disableLookups":true,"edition":"community","env":{"NEO4J_PLUGINS":"[\"apoc\"]"},"fullnameOverride":"musematic-neo4j","minimumClusterSize":1,"name":"musematic-neo4j","neo4j":{"acceptLicenseAgreement":"yes","config":{"dbms.security.procedures.allowlist":"apoc.*","dbms.security.procedures.unrestricted":"apoc.*","server.memory.heap.initial_size":"1G","server.memory.heap.max_size":"2G","server.memory.pagecache.size":"1G"},"edition":"community","env":{"NEO4J_PLUGINS":"[\"apoc\"]"},"minimumClusterSize":1,"name":"musematic-neo4j","password":"","passwordFromSecret":"neo4j-credentials","resources":{"cpu":"1","limits":{"cpu":"2","memory":"4Gi"},"memory":"3Gi","requests":{"cpu":"1","memory":"3Gi"}}},"password":"","passwordFromSecret":"neo4j-credentials","resources":{"cpu":"1","limits":{"cpu":"2","memory":"4Gi"},"memory":"3Gi","requests":{"cpu":"1","memory":"3Gi"}},"volumes":{"data":{"dynamic":{"requests":{"storage":"20Gi"},"storageClassName":"standard"},"mode":"dynamic"}}}` | Configures `neo4j` for the neo4j chart. |
| neo4j.acceptLicenseAgreement | string | `"yes"` | Configures `neo4j.acceptLicenseAgreement` for the neo4j chart. |
| neo4j.config | object | `{"dbms.security.procedures.allowlist":"apoc.*","dbms.security.procedures.unrestricted":"apoc.*","server.memory.heap.initial_size":"1G","server.memory.heap.max_size":"2G","server.memory.pagecache.size":"1G"}` | Configures `neo4j.config` for the neo4j chart. |
| neo4j.config."dbms.security.procedures.allowlist" | string | `"apoc.*"` | Configures `neo4j.config.dbms.security.procedures.allowlist` for the neo4j chart. |
| neo4j.config."dbms.security.procedures.unrestricted" | string | `"apoc.*"` | Configures `neo4j.config.dbms.security.procedures.unrestricted` for the neo4j chart. |
| neo4j.config."server.memory.heap.initial_size" | string | `"1G"` | Configures `neo4j.config.server.memory.heap.initial_size` for the neo4j chart. |
| neo4j.config."server.memory.heap.max_size" | string | `"2G"` | Configures `neo4j.config.server.memory.heap.max_size` for the neo4j chart. |
| neo4j.config."server.memory.pagecache.size" | string | `"1G"` | Configures `neo4j.config.server.memory.pagecache.size` for the neo4j chart. |
| neo4j.disableLookups | bool | `true` | Configures `neo4j.disableLookups` for the neo4j chart. |
| neo4j.edition | string | `"community"` | Configures `neo4j.edition` for the neo4j chart. |
| neo4j.env | object | `{"NEO4J_PLUGINS":"[\"apoc\"]"}` | Configures `neo4j.env` for the neo4j chart. |
| neo4j.env.NEO4J_PLUGINS | string | `"[\"apoc\"]"` | Configures `neo4j.env.NEO4J_PLUGINS` for the neo4j chart. |
| neo4j.fullnameOverride | string | `"musematic-neo4j"` | Configures `neo4j.fullnameOverride` for the neo4j chart. |
| neo4j.minimumClusterSize | int | `1` | Configures `neo4j.minimumClusterSize` for the neo4j chart. |
| neo4j.name | string | `"musematic-neo4j"` | Configures `neo4j.name` for the neo4j chart. |
| neo4j.neo4j | object | `{"acceptLicenseAgreement":"yes","config":{"dbms.security.procedures.allowlist":"apoc.*","dbms.security.procedures.unrestricted":"apoc.*","server.memory.heap.initial_size":"1G","server.memory.heap.max_size":"2G","server.memory.pagecache.size":"1G"},"edition":"community","env":{"NEO4J_PLUGINS":"[\"apoc\"]"},"minimumClusterSize":1,"name":"musematic-neo4j","password":"","passwordFromSecret":"neo4j-credentials","resources":{"cpu":"1","limits":{"cpu":"2","memory":"4Gi"},"memory":"3Gi","requests":{"cpu":"1","memory":"3Gi"}}}` | Configures `neo4j.neo4j` for the neo4j chart. |
| neo4j.neo4j.acceptLicenseAgreement | string | `"yes"` | Configures `neo4j.neo4j.acceptLicenseAgreement` for the neo4j chart. |
| neo4j.neo4j.config | object | `{"dbms.security.procedures.allowlist":"apoc.*","dbms.security.procedures.unrestricted":"apoc.*","server.memory.heap.initial_size":"1G","server.memory.heap.max_size":"2G","server.memory.pagecache.size":"1G"}` | Configures `neo4j.neo4j.config` for the neo4j chart. |
| neo4j.neo4j.config."dbms.security.procedures.allowlist" | string | `"apoc.*"` | Configures `neo4j.neo4j.config.dbms.security.procedures.allowlist` for the neo4j chart. |
| neo4j.neo4j.config."dbms.security.procedures.unrestricted" | string | `"apoc.*"` | Configures `neo4j.neo4j.config.dbms.security.procedures.unrestricted` for the neo4j chart. |
| neo4j.neo4j.config."server.memory.heap.initial_size" | string | `"1G"` | Configures `neo4j.neo4j.config.server.memory.heap.initial_size` for the neo4j chart. |
| neo4j.neo4j.config."server.memory.heap.max_size" | string | `"2G"` | Configures `neo4j.neo4j.config.server.memory.heap.max_size` for the neo4j chart. |
| neo4j.neo4j.config."server.memory.pagecache.size" | string | `"1G"` | Configures `neo4j.neo4j.config.server.memory.pagecache.size` for the neo4j chart. |
| neo4j.neo4j.edition | string | `"community"` | Configures `neo4j.neo4j.edition` for the neo4j chart. |
| neo4j.neo4j.env | object | `{"NEO4J_PLUGINS":"[\"apoc\"]"}` | Configures `neo4j.neo4j.env` for the neo4j chart. |
| neo4j.neo4j.env.NEO4J_PLUGINS | string | `"[\"apoc\"]"` | Configures `neo4j.neo4j.env.NEO4J_PLUGINS` for the neo4j chart. |
| neo4j.neo4j.minimumClusterSize | int | `1` | Configures `neo4j.neo4j.minimumClusterSize` for the neo4j chart. |
| neo4j.neo4j.name | string | `"musematic-neo4j"` | Configures `neo4j.neo4j.name` for the neo4j chart. |
| neo4j.neo4j.password | string | `""` | Configures `neo4j.neo4j.password` for the neo4j chart. |
| neo4j.neo4j.passwordFromSecret | string | `"neo4j-credentials"` | Configures `neo4j.neo4j.passwordFromSecret` for the neo4j chart. |
| neo4j.neo4j.resources | object | `{"cpu":"1","limits":{"cpu":"2","memory":"4Gi"},"memory":"3Gi","requests":{"cpu":"1","memory":"3Gi"}}` | Configures `neo4j.neo4j.resources` for the neo4j chart. |
| neo4j.neo4j.resources.cpu | string | `"1"` | Configures `neo4j.neo4j.resources.cpu` for the neo4j chart. |
| neo4j.neo4j.resources.limits | object | `{"cpu":"2","memory":"4Gi"}` | Configures `neo4j.neo4j.resources.limits` for the neo4j chart. |
| neo4j.neo4j.resources.limits.cpu | string | `"2"` | Configures `neo4j.neo4j.resources.limits.cpu` for the neo4j chart. |
| neo4j.neo4j.resources.limits.memory | string | `"4Gi"` | Configures `neo4j.neo4j.resources.limits.memory` for the neo4j chart. |
| neo4j.neo4j.resources.memory | string | `"3Gi"` | Configures `neo4j.neo4j.resources.memory` for the neo4j chart. |
| neo4j.neo4j.resources.requests | object | `{"cpu":"1","memory":"3Gi"}` | Configures `neo4j.neo4j.resources.requests` for the neo4j chart. |
| neo4j.neo4j.resources.requests.cpu | string | `"1"` | Configures `neo4j.neo4j.resources.requests.cpu` for the neo4j chart. |
| neo4j.neo4j.resources.requests.memory | string | `"3Gi"` | Configures `neo4j.neo4j.resources.requests.memory` for the neo4j chart. |
| neo4j.password | string | `""` | Configures `neo4j.password` for the neo4j chart. |
| neo4j.passwordFromSecret | string | `"neo4j-credentials"` | Configures `neo4j.passwordFromSecret` for the neo4j chart. |
| neo4j.resources | object | `{"cpu":"1","limits":{"cpu":"2","memory":"4Gi"},"memory":"3Gi","requests":{"cpu":"1","memory":"3Gi"}}` | Configures `neo4j.resources` for the neo4j chart. |
| neo4j.resources.cpu | string | `"1"` | Configures `neo4j.resources.cpu` for the neo4j chart. |
| neo4j.resources.limits | object | `{"cpu":"2","memory":"4Gi"}` | Configures `neo4j.resources.limits` for the neo4j chart. |
| neo4j.resources.limits.cpu | string | `"2"` | Configures `neo4j.resources.limits.cpu` for the neo4j chart. |
| neo4j.resources.limits.memory | string | `"4Gi"` | Configures `neo4j.resources.limits.memory` for the neo4j chart. |
| neo4j.resources.memory | string | `"3Gi"` | Configures `neo4j.resources.memory` for the neo4j chart. |
| neo4j.resources.requests | object | `{"cpu":"1","memory":"3Gi"}` | Configures `neo4j.resources.requests` for the neo4j chart. |
| neo4j.resources.requests.cpu | string | `"1"` | Configures `neo4j.resources.requests.cpu` for the neo4j chart. |
| neo4j.resources.requests.memory | string | `"3Gi"` | Configures `neo4j.resources.requests.memory` for the neo4j chart. |
| neo4j.volumes | object | `{"data":{"dynamic":{"requests":{"storage":"20Gi"},"storageClassName":"standard"},"mode":"dynamic"}}` | Configures `neo4j.volumes` for the neo4j chart. |
| neo4j.volumes.data | object | `{"dynamic":{"requests":{"storage":"20Gi"},"storageClassName":"standard"},"mode":"dynamic"}` | Configures `neo4j.volumes.data` for the neo4j chart. |
| neo4j.volumes.data.dynamic | object | `{"requests":{"storage":"20Gi"},"storageClassName":"standard"}` | Configures `neo4j.volumes.data.dynamic` for the neo4j chart. |
| neo4j.volumes.data.dynamic.requests | object | `{"storage":"20Gi"}` | Configures `neo4j.volumes.data.dynamic.requests` for the neo4j chart. |
| neo4j.volumes.data.dynamic.requests.storage | string | `"20Gi"` | Configures `neo4j.volumes.data.dynamic.requests.storage` for the neo4j chart. |
| neo4j.volumes.data.dynamic.storageClassName | string | `"standard"` | Configures `neo4j.volumes.data.dynamic.storageClassName` for the neo4j chart. |
| neo4j.volumes.data.mode | string | `"dynamic"` | Configures `neo4j.volumes.data.mode` for the neo4j chart. |
| networkPolicy | object | `{"enabled":true}` | Configures `networkPolicy` for the neo4j chart. |
| networkPolicy.enabled | bool | `true` | Configures `networkPolicy.enabled` for the neo4j chart. |
| persistence | object | `{"size":"20Gi","storageClassName":"standard"}` | Configures `persistence` for the neo4j chart. |
| persistence.size | string | `"20Gi"` | Configures `persistence.size` for the neo4j chart. |
| persistence.storageClassName | string | `"standard"` | Configures `persistence.storageClassName` for the neo4j chart. |
| schemaInit | object | `{"enabled":true,"image":"neo4j:5.21.2-enterprise","retries":60,"retryIntervalSeconds":5}` | Configures `schemaInit` for the neo4j chart. |
| schemaInit.enabled | bool | `true` | Configures `schemaInit.enabled` for the neo4j chart. |
| schemaInit.image | string | `"neo4j:5.21.2-enterprise"` | Configures `schemaInit.image` for the neo4j chart. |
| schemaInit.retries | int | `60` | Configures `schemaInit.retries` for the neo4j chart. |
| schemaInit.retryIntervalSeconds | int | `5` | Configures `schemaInit.retryIntervalSeconds` for the neo4j chart. |
| service | object | `{"boltPort":7687,"httpPort":7474,"type":"ClusterIP"}` | Configures `service` for the neo4j chart. |
| service.boltPort | int | `7687` | Configures `service.boltPort` for the neo4j chart. |
| service.httpPort | int | `7474` | Configures `service.httpPort` for the neo4j chart. |
| service.type | string | `"ClusterIP"` | Configures `service.type` for the neo4j chart. |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.13.1](https://github.com/norwoodj/helm-docs/releases/v1.13.1)
