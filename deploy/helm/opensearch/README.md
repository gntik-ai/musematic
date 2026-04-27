# musematic-opensearch

![Version: 0.1.0](https://img.shields.io/badge/Version-0.1.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 2.18.0](https://img.shields.io/badge/AppVersion-2.18.0-informational?style=flat-square)

OpenSearch full-text search for the Musematic platform.

## Requirements

| Repository | Name | Version |
|------------|------|---------|
| https://opensearch-project.github.io/helm-charts | opensearch | ~2.18.0 |
| https://opensearch-project.github.io/helm-charts | opensearch-dashboards | ~2.18.0 |

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| credentials | object | `{"password":"","username":"admin"}` | Configures `credentials` for the opensearch chart. |
| credentials.password | string | `""` | Configures `credentials.password` for the opensearch chart. |
| credentials.username | string | `"admin"` | Configures `credentials.username` for the opensearch chart. |
| initJob | object | `{"backoffLimit":4,"enabled":true,"image":{"repository":"python","tag":"3.12-slim"},"opensearchUrl":"http://musematic-opensearch:9200","snapshotRepository":{"basePath":"backups/opensearch","bucket":"backups","endpoint":"http://musematic-minio.platform-data:9000","name":"opensearch-backups","region":"us-east-1","type":"s3"}}` | Configures `initJob` for the opensearch chart. |
| initJob.backoffLimit | int | `4` | Configures `initJob.backoffLimit` for the opensearch chart. |
| initJob.enabled | bool | `true` | Configures `initJob.enabled` for the opensearch chart. |
| initJob.image | object | `{"repository":"python","tag":"3.12-slim"}` | Configures `initJob.image` for the opensearch chart. |
| initJob.image.repository | string | `"python"` | Configures `initJob.image.repository` for the opensearch chart. |
| initJob.image.tag | string | `"3.12-slim"` | Configures `initJob.image.tag` for the opensearch chart. |
| initJob.opensearchUrl | string | `"http://musematic-opensearch:9200"` | Configures `initJob.opensearchUrl` for the opensearch chart. |
| initJob.snapshotRepository | object | `{"basePath":"backups/opensearch","bucket":"backups","endpoint":"http://musematic-minio.platform-data:9000","name":"opensearch-backups","region":"us-east-1","type":"s3"}` | Configures `initJob.snapshotRepository` for the opensearch chart. |
| initJob.snapshotRepository.basePath | string | `"backups/opensearch"` | Configures `initJob.snapshotRepository.basePath` for the opensearch chart. |
| initJob.snapshotRepository.bucket | string | `"backups"` | Configures `initJob.snapshotRepository.bucket` for the opensearch chart. |
| initJob.snapshotRepository.endpoint | string | `"http://musematic-minio.platform-data:9000"` | Configures `initJob.snapshotRepository.endpoint` for the opensearch chart. |
| initJob.snapshotRepository.name | string | `"opensearch-backups"` | Configures `initJob.snapshotRepository.name` for the opensearch chart. |
| initJob.snapshotRepository.region | string | `"us-east-1"` | Configures `initJob.snapshotRepository.region` for the opensearch chart. |
| initJob.snapshotRepository.type | string | `"s3"` | Configures `initJob.snapshotRepository.type` for the opensearch chart. |
| networkPolicy | object | `{"enabled":true}` | Configures `networkPolicy` for the opensearch chart. |
| networkPolicy.enabled | bool | `true` | Configures `networkPolicy.enabled` for the opensearch chart. |
| opensearch | object | `{"extraEnvs":[{"name":"OPENSEARCH_JAVA_OPTS","value":"-Xms1g -Xmx1g"},{"name":"DISABLE_SECURITY_PLUGIN","value":"false"},{"name":"AWS_EC2_METADATA_DISABLED","value":"true"},{"name":"AWS_REGION","value":"us-east-1"},{"name":"AWS_DEFAULT_REGION","value":"us-east-1"},{"name":"AWS_ACCESS_KEY_ID","valueFrom":{"secretKeyRef":{"key":"MINIO_ACCESS_KEY","name":"minio-platform-credentials"}}},{"name":"AWS_SECRET_ACCESS_KEY","valueFrom":{"secretKeyRef":{"key":"MINIO_SECRET_KEY","name":"minio-platform-credentials"}}}],"extraInitContainers":[{"command":["/bin/sh","-ec","export OPENSEARCH_PATH_CONF=/tmp/keystore\necho \"$S3_ACCESS_KEY\" | /usr/share/opensearch/bin/opensearch-keystore add -xf s3.client.default.access_key\necho \"$S3_SECRET_KEY\" | /usr/share/opensearch/bin/opensearch-keystore add -xf s3.client.default.secret_key\n"],"env":[{"name":"S3_ACCESS_KEY","valueFrom":{"secretKeyRef":{"key":"MINIO_ACCESS_KEY","name":"minio-platform-credentials"}}},{"name":"S3_SECRET_KEY","valueFrom":{"secretKeyRef":{"key":"MINIO_SECRET_KEY","name":"minio-platform-credentials"}}}],"image":"opensearchproject/opensearch:2.18.0","name":"configure-s3-keystore","volumeMounts":[{"mountPath":"/tmp/keystore","name":"keystore"}]}],"extraVolumeMounts":[{"mountPath":"/usr/share/opensearch/config/synonyms","name":"synonyms","readOnly":true}],"extraVolumes":[{"configMap":{"name":"opensearch-synonyms"},"name":"synonyms"}],"fullnameOverride":"musematic-opensearch","image":{"repository":"opensearchproject/opensearch","tag":"2.18.0"},"keystore":[{"secretName":"opensearch-keystore-bootstrap"}],"masterService":"musematic-opensearch","persistence":{"enabled":true,"size":"10Gi","storageClass":""},"plugins":{"enabled":true,"installList":["analysis-icu","repository-s3"]},"replicas":1,"resources":{"limits":{"cpu":"1","memory":"2Gi"},"requests":{"cpu":"500m","memory":"2Gi"}},"service":{"port":9200,"type":"ClusterIP"}}` | Configures `opensearch` for the opensearch chart. |
| opensearch-dashboards | object | `{"enabled":true,"extraEnvs":[{"name":"OPENSEARCH_HOSTS","value":"[\"http://musematic-opensearch:9200\"]"},{"name":"DISABLE_SECURITY_DASHBOARDS_PLUGIN","value":"false"}],"fullnameOverride":"musematic-opensearch-dashboards","image":{"repository":"opensearchproject/opensearch-dashboards","tag":"2.18.0"},"resources":{"limits":{"cpu":"500m","memory":"512Mi"},"requests":{"cpu":"200m","memory":"512Mi"}}}` | Configures `opensearch-dashboards` for the opensearch chart. |
| opensearch-dashboards.enabled | bool | `true` | Configures `opensearch-dashboards.enabled` for the opensearch chart. |
| opensearch-dashboards.extraEnvs | list | `[{"name":"OPENSEARCH_HOSTS","value":"[\"http://musematic-opensearch:9200\"]"},{"name":"DISABLE_SECURITY_DASHBOARDS_PLUGIN","value":"false"}]` | Configures `opensearch-dashboards.extraEnvs` for the opensearch chart. |
| opensearch-dashboards.extraEnvs[0].value | string | `"[\"http://musematic-opensearch:9200\"]"` | Configures `opensearch-dashboards.extraEnvs.value` for the opensearch chart. |
| opensearch-dashboards.extraEnvs[1].value | string | `"false"` | Configures `opensearch-dashboards.extraEnvs.value` for the opensearch chart. |
| opensearch-dashboards.fullnameOverride | string | `"musematic-opensearch-dashboards"` | Configures `opensearch-dashboards.fullnameOverride` for the opensearch chart. |
| opensearch-dashboards.image | object | `{"repository":"opensearchproject/opensearch-dashboards","tag":"2.18.0"}` | Configures `opensearch-dashboards.image` for the opensearch chart. |
| opensearch-dashboards.image.repository | string | `"opensearchproject/opensearch-dashboards"` | Configures `opensearch-dashboards.image.repository` for the opensearch chart. |
| opensearch-dashboards.image.tag | string | `"2.18.0"` | Configures `opensearch-dashboards.image.tag` for the opensearch chart. |
| opensearch-dashboards.resources | object | `{"limits":{"cpu":"500m","memory":"512Mi"},"requests":{"cpu":"200m","memory":"512Mi"}}` | Configures `opensearch-dashboards.resources` for the opensearch chart. |
| opensearch-dashboards.resources.limits | object | `{"cpu":"500m","memory":"512Mi"}` | Configures `opensearch-dashboards.resources.limits` for the opensearch chart. |
| opensearch-dashboards.resources.limits.cpu | string | `"500m"` | Configures `opensearch-dashboards.resources.limits.cpu` for the opensearch chart. |
| opensearch-dashboards.resources.limits.memory | string | `"512Mi"` | Configures `opensearch-dashboards.resources.limits.memory` for the opensearch chart. |
| opensearch-dashboards.resources.requests | object | `{"cpu":"200m","memory":"512Mi"}` | Configures `opensearch-dashboards.resources.requests` for the opensearch chart. |
| opensearch-dashboards.resources.requests.cpu | string | `"200m"` | Configures `opensearch-dashboards.resources.requests.cpu` for the opensearch chart. |
| opensearch-dashboards.resources.requests.memory | string | `"512Mi"` | Configures `opensearch-dashboards.resources.requests.memory` for the opensearch chart. |
| opensearch.extraEnvs | list | `[{"name":"OPENSEARCH_JAVA_OPTS","value":"-Xms1g -Xmx1g"},{"name":"DISABLE_SECURITY_PLUGIN","value":"false"},{"name":"AWS_EC2_METADATA_DISABLED","value":"true"},{"name":"AWS_REGION","value":"us-east-1"},{"name":"AWS_DEFAULT_REGION","value":"us-east-1"},{"name":"AWS_ACCESS_KEY_ID","valueFrom":{"secretKeyRef":{"key":"MINIO_ACCESS_KEY","name":"minio-platform-credentials"}}},{"name":"AWS_SECRET_ACCESS_KEY","valueFrom":{"secretKeyRef":{"key":"MINIO_SECRET_KEY","name":"minio-platform-credentials"}}}]` | Configures `opensearch.extraEnvs` for the opensearch chart. |
| opensearch.extraEnvs[0].value | string | `"-Xms1g -Xmx1g"` | Configures `opensearch.extraEnvs.value` for the opensearch chart. |
| opensearch.extraEnvs[1].value | string | `"false"` | Configures `opensearch.extraEnvs.value` for the opensearch chart. |
| opensearch.extraEnvs[2].value | string | `"true"` | Configures `opensearch.extraEnvs.value` for the opensearch chart. |
| opensearch.extraEnvs[3].value | string | `"us-east-1"` | Configures `opensearch.extraEnvs.value` for the opensearch chart. |
| opensearch.extraEnvs[4].value | string | `"us-east-1"` | Configures `opensearch.extraEnvs.value` for the opensearch chart. |
| opensearch.extraEnvs[5].valueFrom | object | `{"secretKeyRef":{"key":"MINIO_ACCESS_KEY","name":"minio-platform-credentials"}}` | Configures `opensearch.extraEnvs.valueFrom` for the opensearch chart. |
| opensearch.extraEnvs[5].valueFrom.secretKeyRef | object | `{"key":"MINIO_ACCESS_KEY","name":"minio-platform-credentials"}` | Configures `opensearch.extraEnvs.valueFrom.secretKeyRef` for the opensearch chart. |
| opensearch.extraEnvs[5].valueFrom.secretKeyRef.key | string | `"MINIO_ACCESS_KEY"` | Configures `opensearch.extraEnvs.valueFrom.secretKeyRef.key` for the opensearch chart. |
| opensearch.extraEnvs[5].valueFrom.secretKeyRef.name | string | `"minio-platform-credentials"` | Configures `opensearch.extraEnvs.valueFrom.secretKeyRef.name` for the opensearch chart. |
| opensearch.extraEnvs[6].valueFrom | object | `{"secretKeyRef":{"key":"MINIO_SECRET_KEY","name":"minio-platform-credentials"}}` | Configures `opensearch.extraEnvs.valueFrom` for the opensearch chart. |
| opensearch.extraEnvs[6].valueFrom.secretKeyRef | object | `{"key":"MINIO_SECRET_KEY","name":"minio-platform-credentials"}` | Configures `opensearch.extraEnvs.valueFrom.secretKeyRef` for the opensearch chart. |
| opensearch.extraEnvs[6].valueFrom.secretKeyRef.key | string | `"MINIO_SECRET_KEY"` | Configures `opensearch.extraEnvs.valueFrom.secretKeyRef.key` for the opensearch chart. |
| opensearch.extraEnvs[6].valueFrom.secretKeyRef.name | string | `"minio-platform-credentials"` | Configures `opensearch.extraEnvs.valueFrom.secretKeyRef.name` for the opensearch chart. |
| opensearch.extraInitContainers | list | `[{"command":["/bin/sh","-ec","export OPENSEARCH_PATH_CONF=/tmp/keystore\necho \"$S3_ACCESS_KEY\" | /usr/share/opensearch/bin/opensearch-keystore add -xf s3.client.default.access_key\necho \"$S3_SECRET_KEY\" | /usr/share/opensearch/bin/opensearch-keystore add -xf s3.client.default.secret_key\n"],"env":[{"name":"S3_ACCESS_KEY","valueFrom":{"secretKeyRef":{"key":"MINIO_ACCESS_KEY","name":"minio-platform-credentials"}}},{"name":"S3_SECRET_KEY","valueFrom":{"secretKeyRef":{"key":"MINIO_SECRET_KEY","name":"minio-platform-credentials"}}}],"image":"opensearchproject/opensearch:2.18.0","name":"configure-s3-keystore","volumeMounts":[{"mountPath":"/tmp/keystore","name":"keystore"}]}]` | Configures `opensearch.extraInitContainers` for the opensearch chart. |
| opensearch.extraInitContainers[0].command | list | `["/bin/sh","-ec","export OPENSEARCH_PATH_CONF=/tmp/keystore\necho \"$S3_ACCESS_KEY\" | /usr/share/opensearch/bin/opensearch-keystore add -xf s3.client.default.access_key\necho \"$S3_SECRET_KEY\" | /usr/share/opensearch/bin/opensearch-keystore add -xf s3.client.default.secret_key\n"]` | Configures `opensearch.extraInitContainers.command` for the opensearch chart. |
| opensearch.extraInitContainers[0].env | list | `[{"name":"S3_ACCESS_KEY","valueFrom":{"secretKeyRef":{"key":"MINIO_ACCESS_KEY","name":"minio-platform-credentials"}}},{"name":"S3_SECRET_KEY","valueFrom":{"secretKeyRef":{"key":"MINIO_SECRET_KEY","name":"minio-platform-credentials"}}}]` | Configures `opensearch.extraInitContainers.env` for the opensearch chart. |
| opensearch.extraInitContainers[0].env[0].valueFrom | object | `{"secretKeyRef":{"key":"MINIO_ACCESS_KEY","name":"minio-platform-credentials"}}` | Configures `opensearch.extraInitContainers.env.valueFrom` for the opensearch chart. |
| opensearch.extraInitContainers[0].env[0].valueFrom.secretKeyRef | object | `{"key":"MINIO_ACCESS_KEY","name":"minio-platform-credentials"}` | Configures `opensearch.extraInitContainers.env.valueFrom.secretKeyRef` for the opensearch chart. |
| opensearch.extraInitContainers[0].env[0].valueFrom.secretKeyRef.key | string | `"MINIO_ACCESS_KEY"` | Configures `opensearch.extraInitContainers.env.valueFrom.secretKeyRef.key` for the opensearch chart. |
| opensearch.extraInitContainers[0].env[0].valueFrom.secretKeyRef.name | string | `"minio-platform-credentials"` | Configures `opensearch.extraInitContainers.env.valueFrom.secretKeyRef.name` for the opensearch chart. |
| opensearch.extraInitContainers[0].env[1].valueFrom | object | `{"secretKeyRef":{"key":"MINIO_SECRET_KEY","name":"minio-platform-credentials"}}` | Configures `opensearch.extraInitContainers.env.valueFrom` for the opensearch chart. |
| opensearch.extraInitContainers[0].env[1].valueFrom.secretKeyRef | object | `{"key":"MINIO_SECRET_KEY","name":"minio-platform-credentials"}` | Configures `opensearch.extraInitContainers.env.valueFrom.secretKeyRef` for the opensearch chart. |
| opensearch.extraInitContainers[0].env[1].valueFrom.secretKeyRef.key | string | `"MINIO_SECRET_KEY"` | Configures `opensearch.extraInitContainers.env.valueFrom.secretKeyRef.key` for the opensearch chart. |
| opensearch.extraInitContainers[0].env[1].valueFrom.secretKeyRef.name | string | `"minio-platform-credentials"` | Configures `opensearch.extraInitContainers.env.valueFrom.secretKeyRef.name` for the opensearch chart. |
| opensearch.extraInitContainers[0].image | string | `"opensearchproject/opensearch:2.18.0"` | Configures `opensearch.extraInitContainers.image` for the opensearch chart. |
| opensearch.extraInitContainers[0].volumeMounts | list | `[{"mountPath":"/tmp/keystore","name":"keystore"}]` | Configures `opensearch.extraInitContainers.volumeMounts` for the opensearch chart. |
| opensearch.extraInitContainers[0].volumeMounts[0].mountPath | string | `"/tmp/keystore"` | Configures `opensearch.extraInitContainers.volumeMounts.mountPath` for the opensearch chart. |
| opensearch.extraVolumeMounts | list | `[{"mountPath":"/usr/share/opensearch/config/synonyms","name":"synonyms","readOnly":true}]` | Configures `opensearch.extraVolumeMounts` for the opensearch chart. |
| opensearch.extraVolumeMounts[0].mountPath | string | `"/usr/share/opensearch/config/synonyms"` | Configures `opensearch.extraVolumeMounts.mountPath` for the opensearch chart. |
| opensearch.extraVolumeMounts[0].readOnly | bool | `true` | Configures `opensearch.extraVolumeMounts.readOnly` for the opensearch chart. |
| opensearch.extraVolumes | list | `[{"configMap":{"name":"opensearch-synonyms"},"name":"synonyms"}]` | Configures `opensearch.extraVolumes` for the opensearch chart. |
| opensearch.extraVolumes[0].configMap | object | `{"name":"opensearch-synonyms"}` | Configures `opensearch.extraVolumes.configMap` for the opensearch chart. |
| opensearch.extraVolumes[0].configMap.name | string | `"opensearch-synonyms"` | Configures `opensearch.extraVolumes.configMap.name` for the opensearch chart. |
| opensearch.fullnameOverride | string | `"musematic-opensearch"` | Configures `opensearch.fullnameOverride` for the opensearch chart. |
| opensearch.image | object | `{"repository":"opensearchproject/opensearch","tag":"2.18.0"}` | Configures `opensearch.image` for the opensearch chart. |
| opensearch.image.repository | string | `"opensearchproject/opensearch"` | Configures `opensearch.image.repository` for the opensearch chart. |
| opensearch.image.tag | string | `"2.18.0"` | Configures `opensearch.image.tag` for the opensearch chart. |
| opensearch.keystore | list | `[{"secretName":"opensearch-keystore-bootstrap"}]` | Configures `opensearch.keystore` for the opensearch chart. |
| opensearch.masterService | string | `"musematic-opensearch"` | Configures `opensearch.masterService` for the opensearch chart. |
| opensearch.persistence | object | `{"enabled":true,"size":"10Gi","storageClass":""}` | Configures `opensearch.persistence` for the opensearch chart. |
| opensearch.persistence.enabled | bool | `true` | Configures `opensearch.persistence.enabled` for the opensearch chart. |
| opensearch.persistence.size | string | `"10Gi"` | Configures `opensearch.persistence.size` for the opensearch chart. |
| opensearch.persistence.storageClass | string | `""` | Configures `opensearch.persistence.storageClass` for the opensearch chart. |
| opensearch.plugins | object | `{"enabled":true,"installList":["analysis-icu","repository-s3"]}` | Configures `opensearch.plugins` for the opensearch chart. |
| opensearch.plugins.enabled | bool | `true` | Configures `opensearch.plugins.enabled` for the opensearch chart. |
| opensearch.plugins.installList | list | `["analysis-icu","repository-s3"]` | Configures `opensearch.plugins.installList` for the opensearch chart. |
| opensearch.replicas | int | `1` | Configures `opensearch.replicas` for the opensearch chart. |
| opensearch.resources | object | `{"limits":{"cpu":"1","memory":"2Gi"},"requests":{"cpu":"500m","memory":"2Gi"}}` | Configures `opensearch.resources` for the opensearch chart. |
| opensearch.resources.limits | object | `{"cpu":"1","memory":"2Gi"}` | Configures `opensearch.resources.limits` for the opensearch chart. |
| opensearch.resources.limits.cpu | string | `"1"` | Configures `opensearch.resources.limits.cpu` for the opensearch chart. |
| opensearch.resources.limits.memory | string | `"2Gi"` | Configures `opensearch.resources.limits.memory` for the opensearch chart. |
| opensearch.resources.requests | object | `{"cpu":"500m","memory":"2Gi"}` | Configures `opensearch.resources.requests` for the opensearch chart. |
| opensearch.resources.requests.cpu | string | `"500m"` | Configures `opensearch.resources.requests.cpu` for the opensearch chart. |
| opensearch.resources.requests.memory | string | `"2Gi"` | Configures `opensearch.resources.requests.memory` for the opensearch chart. |
| opensearch.service | object | `{"port":9200,"type":"ClusterIP"}` | Configures `opensearch.service` for the opensearch chart. |
| opensearch.service.port | int | `9200` | Configures `opensearch.service.port` for the opensearch chart. |
| opensearch.service.type | string | `"ClusterIP"` | Configures `opensearch.service.type` for the opensearch chart. |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.13.1](https://github.com/norwoodj/helm-docs/releases/v1.13.1)
