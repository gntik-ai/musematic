# musematic-control-plane

![Version: 0.1.0](https://img.shields.io/badge/Version-0.1.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 0.1.0](https://img.shields.io/badge/AppVersion-0.1.0-informational?style=flat-square)

Control-plane deployment assets for Musematic.

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| api | object | `{"enabled":true,"replicaCount":1,"service":{"nodePort":null,"port":8000,"type":"ClusterIP"}}` | Configures `api` for the control-plane chart. |
| api.enabled | bool | `true` | Configures `api.enabled` for the control-plane chart. |
| api.replicaCount | int | `1` | Configures `api.replicaCount` for the control-plane chart. |
| api.service | object | `{"nodePort":null,"port":8000,"type":"ClusterIP"}` | Configures `api.service` for the control-plane chart. |
| api.service.nodePort | string | `nil` | Configures `api.service.nodePort` for the control-plane chart. |
| api.service.port | int | `8000` | Configures `api.service.port` for the control-plane chart. |
| api.service.type | string | `"ClusterIP"` | Configures `api.service.type` for the control-plane chart. |
| auth | object | `{"oauth":{"github":{"authorizeUrl":"https://github.com/login/oauth/authorize","emailsUrl":"https://api.github.com/user/emails","orgMembershipUrlTemplate":"https://api.github.com/user/memberships/orgs/{org}","teamsUrl":"https://api.github.com/user/teams","tokenUrl":"https://github.com/login/oauth/access_token","userUrl":"https://api.github.com/user"},"google":{"authorizeUrl":"https://accounts.google.com/o/oauth2/v2/auth","tokenInfoUrl":"https://oauth2.googleapis.com/tokeninfo","tokenUrl":"https://oauth2.googleapis.com/token"},"rateLimitMax":10,"rateLimitWindow":60}}` | Configures `auth` for the control-plane chart. |
| auth.oauth | object | `{"github":{"authorizeUrl":"https://github.com/login/oauth/authorize","emailsUrl":"https://api.github.com/user/emails","orgMembershipUrlTemplate":"https://api.github.com/user/memberships/orgs/{org}","teamsUrl":"https://api.github.com/user/teams","tokenUrl":"https://github.com/login/oauth/access_token","userUrl":"https://api.github.com/user"},"google":{"authorizeUrl":"https://accounts.google.com/o/oauth2/v2/auth","tokenInfoUrl":"https://oauth2.googleapis.com/tokeninfo","tokenUrl":"https://oauth2.googleapis.com/token"},"rateLimitMax":10,"rateLimitWindow":60}` | Configures `auth.oauth` for the control-plane chart. |
| auth.oauth.github | object | `{"authorizeUrl":"https://github.com/login/oauth/authorize","emailsUrl":"https://api.github.com/user/emails","orgMembershipUrlTemplate":"https://api.github.com/user/memberships/orgs/{org}","teamsUrl":"https://api.github.com/user/teams","tokenUrl":"https://github.com/login/oauth/access_token","userUrl":"https://api.github.com/user"}` | Configures `auth.oauth.github` for the control-plane chart. |
| auth.oauth.github.authorizeUrl | string | `"https://github.com/login/oauth/authorize"` | Configures `auth.oauth.github.authorizeUrl` for the control-plane chart. |
| auth.oauth.github.emailsUrl | string | `"https://api.github.com/user/emails"` | Configures `auth.oauth.github.emailsUrl` for the control-plane chart. |
| auth.oauth.github.orgMembershipUrlTemplate | string | `"https://api.github.com/user/memberships/orgs/{org}"` | Configures `auth.oauth.github.orgMembershipUrlTemplate` for the control-plane chart. |
| auth.oauth.github.teamsUrl | string | `"https://api.github.com/user/teams"` | Configures `auth.oauth.github.teamsUrl` for the control-plane chart. |
| auth.oauth.github.tokenUrl | string | `"https://github.com/login/oauth/access_token"` | Configures `auth.oauth.github.tokenUrl` for the control-plane chart. |
| auth.oauth.github.userUrl | string | `"https://api.github.com/user"` | Configures `auth.oauth.github.userUrl` for the control-plane chart. |
| auth.oauth.google | object | `{"authorizeUrl":"https://accounts.google.com/o/oauth2/v2/auth","tokenInfoUrl":"https://oauth2.googleapis.com/tokeninfo","tokenUrl":"https://oauth2.googleapis.com/token"}` | Configures `auth.oauth.google` for the control-plane chart. |
| auth.oauth.google.authorizeUrl | string | `"https://accounts.google.com/o/oauth2/v2/auth"` | Configures `auth.oauth.google.authorizeUrl` for the control-plane chart. |
| auth.oauth.google.tokenInfoUrl | string | `"https://oauth2.googleapis.com/tokeninfo"` | Configures `auth.oauth.google.tokenInfoUrl` for the control-plane chart. |
| auth.oauth.google.tokenUrl | string | `"https://oauth2.googleapis.com/token"` | Configures `auth.oauth.google.tokenUrl` for the control-plane chart. |
| auth.oauth.rateLimitMax | int | `10` | Configures `auth.oauth.rateLimitMax` for the control-plane chart. |
| auth.oauth.rateLimitWindow | int | `60` | Configures `auth.oauth.rateLimitWindow` for the control-plane chart. |
| common | object | `{"extraEnv":{},"featureE2EMode":false,"mockLlmEnabled":false,"otelExporterEndpoint":"http://otel-collector.platform-observability.svc.cluster.local:4318","otelResourceAttributes":"deployment.environment=production","otelServiceName":"control-plane","resources":{"limits":{"cpu":"1","memory":"512Mi"},"requests":{"cpu":"250m","memory":"256Mi"}},"wsClientBufferSize":1000,"wsHeartbeatIntervalSeconds":30,"wsHeartbeatTimeoutSeconds":10,"zeroTrustVisibility":false}` | Configures `common` for the control-plane chart. |
| common.extraEnv | object | `{}` | Configures `common.extraEnv` for the control-plane chart. |
| common.featureE2EMode | bool | `false` | Configures `common.featureE2EMode` for the control-plane chart. |
| common.mockLlmEnabled | bool | `false` | Configures `common.mockLlmEnabled` for the control-plane chart. |
| common.otelExporterEndpoint | string | `"http://otel-collector.platform-observability.svc.cluster.local:4318"` | Configures `common.otelExporterEndpoint` for the control-plane chart. |
| common.otelResourceAttributes | string | `"deployment.environment=production"` | Configures `common.otelResourceAttributes` for the control-plane chart. |
| common.otelServiceName | string | `"control-plane"` | Configures `common.otelServiceName` for the control-plane chart. |
| common.resources | object | `{"limits":{"cpu":"1","memory":"512Mi"},"requests":{"cpu":"250m","memory":"256Mi"}}` | Configures `common.resources` for the control-plane chart. |
| common.resources.limits | object | `{"cpu":"1","memory":"512Mi"}` | Configures `common.resources.limits` for the control-plane chart. |
| common.resources.limits.cpu | string | `"1"` | Configures `common.resources.limits.cpu` for the control-plane chart. |
| common.resources.limits.memory | string | `"512Mi"` | Configures `common.resources.limits.memory` for the control-plane chart. |
| common.resources.requests | object | `{"cpu":"250m","memory":"256Mi"}` | Configures `common.resources.requests` for the control-plane chart. |
| common.resources.requests.cpu | string | `"250m"` | Configures `common.resources.requests.cpu` for the control-plane chart. |
| common.resources.requests.memory | string | `"256Mi"` | Configures `common.resources.requests.memory` for the control-plane chart. |
| common.wsClientBufferSize | int | `1000` | Configures `common.wsClientBufferSize` for the control-plane chart. |
| common.wsHeartbeatIntervalSeconds | int | `30` | Configures `common.wsHeartbeatIntervalSeconds` for the control-plane chart. |
| common.wsHeartbeatTimeoutSeconds | int | `10` | Configures `common.wsHeartbeatTimeoutSeconds` for the control-plane chart. |
| common.zeroTrustVisibility | bool | `false` | Configures `common.zeroTrustVisibility` for the control-plane chart. |
| connections | object | `{"authJwtAlgorithm":"HS256","authJwtSecretKey":"change-me","authMfaEncryptionKey":"","clickhouseDatabase":"default","clickhouseHost":"musematic-clickhouse.platform.svc.cluster.local","clickhousePassword":"","clickhousePort":8123,"clickhouseUser":"default","grpcReasoningEngine":"reasoning-engine.platform.svc.cluster.local:50052","grpcRuntimeController":"musematic-runtime-controller.platform.svc.cluster.local:50051","grpcSandboxManager":"sandbox-manager.platform.svc.cluster.local:50053","grpcSimulationController":"musematic-simulation-controller.platform.svc.cluster.local:50055","kafkaBrokers":"musematic-kafka-kafka-bootstrap.platform-data.svc.cluster.local:9092","neo4jPassword":"neo4j","neo4jUri":"bolt://musematic-neo4j.platform.svc.cluster.local:7687","neo4jUser":"neo4j","opensearchHosts":"http://musematic-opensearch.platform.svc.cluster.local:9200","opensearchPassword":"admin","opensearchUsername":"admin","platformStaffPostgresDsn":"","postgresDsn":"postgresql+asyncpg://musematic:change-me@musematic-postgres-rw.platform-data.svc.cluster.local:5432/musematic","qdrantGrpcPort":6334,"qdrantHost":"musematic-qdrant.platform.svc.cluster.local","qdrantPort":6333,"redisTestMode":"cluster","redisUrl":"redis://:change-me@musematic-redis.platform.svc.cluster.local:6379","rotatingSecrets":{},"s3AccessKey":"platform","s3BucketPrefix":"platform","s3EndpointUrl":"http://musematic-minio.platform-data.svc.cluster.local:9000","s3Provider":"generic","s3Region":"us-east-1","s3SecretKey":"change-me","s3UsePathStyle":true}` | Configures `connections` for the control-plane chart. |
| connections.authJwtAlgorithm | string | `"HS256"` | Configures `connections.authJwtAlgorithm` for the control-plane chart. |
| connections.authJwtSecretKey | string | `"change-me"` | Configures `connections.authJwtSecretKey` for the control-plane chart. |
| connections.authMfaEncryptionKey | string | `""` | Configures `connections.authMfaEncryptionKey` for the control-plane chart. |
| connections.clickhouseDatabase | string | `"default"` | Configures `connections.clickhouseDatabase` for the control-plane chart. |
| connections.clickhouseHost | string | `"musematic-clickhouse.platform.svc.cluster.local"` | Configures `connections.clickhouseHost` for the control-plane chart. |
| connections.clickhousePassword | string | `""` | Configures `connections.clickhousePassword` for the control-plane chart. |
| connections.clickhousePort | int | `8123` | Configures `connections.clickhousePort` for the control-plane chart. |
| connections.clickhouseUser | string | `"default"` | Configures `connections.clickhouseUser` for the control-plane chart. |
| connections.grpcReasoningEngine | string | `"reasoning-engine.platform.svc.cluster.local:50052"` | Configures `connections.grpcReasoningEngine` for the control-plane chart. |
| connections.grpcRuntimeController | string | `"musematic-runtime-controller.platform.svc.cluster.local:50051"` | Configures `connections.grpcRuntimeController` for the control-plane chart. |
| connections.grpcSandboxManager | string | `"sandbox-manager.platform.svc.cluster.local:50053"` | Configures `connections.grpcSandboxManager` for the control-plane chart. |
| connections.grpcSimulationController | string | `"musematic-simulation-controller.platform.svc.cluster.local:50055"` | Configures `connections.grpcSimulationController` for the control-plane chart. |
| connections.kafkaBrokers | string | `"musematic-kafka-kafka-bootstrap.platform-data.svc.cluster.local:9092"` | Configures `connections.kafkaBrokers` for the control-plane chart. |
| connections.neo4jPassword | string | `"neo4j"` | Configures `connections.neo4jPassword` for the control-plane chart. |
| connections.neo4jUri | string | `"bolt://musematic-neo4j.platform.svc.cluster.local:7687"` | Configures `connections.neo4jUri` for the control-plane chart. |
| connections.neo4jUser | string | `"neo4j"` | Configures `connections.neo4jUser` for the control-plane chart. |
| connections.opensearchHosts | string | `"http://musematic-opensearch.platform.svc.cluster.local:9200"` | Configures `connections.opensearchHosts` for the control-plane chart. |
| connections.opensearchPassword | string | `"admin"` | Configures `connections.opensearchPassword` for the control-plane chart. |
| connections.opensearchUsername | string | `"admin"` | Configures `connections.opensearchUsername` for the control-plane chart. |
| connections.platformStaffPostgresDsn | string | `""` | Configures `connections.platformStaffPostgresDsn` for the control-plane chart. |
| connections.postgresDsn | string | `"postgresql+asyncpg://musematic:change-me@musematic-postgres-rw.platform-data.svc.cluster.local:5432/musematic"` | Configures `connections.postgresDsn` for the control-plane chart. |
| connections.qdrantGrpcPort | int | `6334` | Configures `connections.qdrantGrpcPort` for the control-plane chart. |
| connections.qdrantHost | string | `"musematic-qdrant.platform.svc.cluster.local"` | Configures `connections.qdrantHost` for the control-plane chart. |
| connections.qdrantPort | int | `6333` | Configures `connections.qdrantPort` for the control-plane chart. |
| connections.redisTestMode | string | `"cluster"` | Configures `connections.redisTestMode` for the control-plane chart. |
| connections.redisUrl | string | `"redis://:change-me@musematic-redis.platform.svc.cluster.local:6379"` | Configures `connections.redisUrl` for the control-plane chart. |
| connections.rotatingSecrets | object | `{}` | Configures `connections.rotatingSecrets` for the control-plane chart. |
| connections.s3AccessKey | string | `"platform"` | Configures `connections.s3AccessKey` for the control-plane chart. |
| connections.s3BucketPrefix | string | `"platform"` | Configures `connections.s3BucketPrefix` for the control-plane chart. |
| connections.s3EndpointUrl | string | `"http://musematic-minio.platform-data.svc.cluster.local:9000"` | Configures `connections.s3EndpointUrl` for the control-plane chart. |
| connections.s3Provider | string | `"generic"` | Configures `connections.s3Provider` for the control-plane chart. |
| connections.s3Region | string | `"us-east-1"` | Configures `connections.s3Region` for the control-plane chart. |
| connections.s3SecretKey | string | `"change-me"` | Configures `connections.s3SecretKey` for the control-plane chart. |
| connections.s3UsePathStyle | bool | `true` | Configures `connections.s3UsePathStyle` for the control-plane chart. |
| image | object | `{"pullPolicy":"IfNotPresent","repository":"ghcr.io/musematic/control-plane","tag":"latest"}` | Configures `image` for the control-plane chart. |
| image.pullPolicy | string | `"IfNotPresent"` | Configures `image.pullPolicy` for the control-plane chart. |
| image.repository | string | `"ghcr.io/musematic/control-plane"` | Configures `image.repository` for the control-plane chart. |
| image.tag | string | `"latest"` | Configures `image.tag` for the control-plane chart. |
| migration | object | `{"backoffLimit":3,"enabled":true,"hook":"pre-install,pre-upgrade","retryAttempts":1,"retryDelaySeconds":5}` | Configures `migration` for the control-plane chart. |
| migration.backoffLimit | int | `3` | Configures `migration.backoffLimit` for the control-plane chart. |
| migration.enabled | bool | `true` | Configures `migration.enabled` for the control-plane chart. |
| migration.hook | string | `"pre-install,pre-upgrade"` | Configures `migration.hook` for the control-plane chart. |
| migration.retryAttempts | int | `1` | Configures `migration.retryAttempts` for the control-plane chart. |
| migration.retryDelaySeconds | int | `5` | Configures `migration.retryDelaySeconds` for the control-plane chart. |
| oauth | object | `{"github":{"allowedOrgs":[],"clientId":"","clientSecretRef":{"key":"client-secret","name":""},"clientSecretVaultPath":"","defaultRole":"member","enabled":false,"forceUpdate":false,"redirectUri":"","requireMfa":false,"teamRoleMappings":{}},"google":{"allowedDomains":[],"clientId":"","clientSecretRef":{"key":"client-secret","name":""},"clientSecretVaultPath":"","defaultRole":"member","enabled":false,"forceUpdate":false,"groupRoleMappings":{},"redirectUri":"","requireMfa":false}}` | Configures environment-variable OAuth provider bootstrap for the control-plane chart. |
| oauth.github | object | `{"allowedOrgs":[],"clientId":"","clientSecretRef":{"key":"client-secret","name":""},"clientSecretVaultPath":"","defaultRole":"member","enabled":false,"forceUpdate":false,"redirectUri":"","requireMfa":false,"teamRoleMappings":{}}` | Configures `oauth.github` for the control-plane chart. |
| oauth.github.allowedOrgs | list | `[]` | Configures `oauth.github.allowedOrgs` for the control-plane chart. |
| oauth.github.clientId | string | `""` | Configures `oauth.github.clientId` for the control-plane chart. |
| oauth.github.clientSecretRef | object | `{"key":"client-secret","name":""}` | Configures `oauth.github.clientSecretRef` for the control-plane chart. |
| oauth.github.clientSecretRef.key | string | `"client-secret"` | Configures `oauth.github.clientSecretRef.key` for the control-plane chart. |
| oauth.github.clientSecretRef.name | string | `""` | Configures `oauth.github.clientSecretRef.name` for the control-plane chart. |
| oauth.github.clientSecretVaultPath | string | `""` | Configures `oauth.github.clientSecretVaultPath` for the control-plane chart. |
| oauth.github.defaultRole | string | `"member"` | Configures `oauth.github.defaultRole` for the control-plane chart. |
| oauth.github.enabled | bool | `false` | Configures `oauth.github.enabled` for the control-plane chart. |
| oauth.github.forceUpdate | bool | `false` | Configures `oauth.github.forceUpdate` for the control-plane chart. |
| oauth.github.redirectUri | string | `""` | Configures `oauth.github.redirectUri` for the control-plane chart. |
| oauth.github.requireMfa | bool | `false` | Configures `oauth.github.requireMfa` for the control-plane chart. |
| oauth.github.teamRoleMappings | object | `{}` | Configures `oauth.github.teamRoleMappings` for the control-plane chart. |
| oauth.google | object | `{"allowedDomains":[],"clientId":"","clientSecretRef":{"key":"client-secret","name":""},"clientSecretVaultPath":"","defaultRole":"member","enabled":false,"forceUpdate":false,"groupRoleMappings":{},"redirectUri":"","requireMfa":false}` | Configures `oauth.google` for the control-plane chart. |
| oauth.google.allowedDomains | list | `[]` | Configures `oauth.google.allowedDomains` for the control-plane chart. |
| oauth.google.clientId | string | `""` | Configures `oauth.google.clientId` for the control-plane chart. |
| oauth.google.clientSecretRef | object | `{"key":"client-secret","name":""}` | Configures `oauth.google.clientSecretRef` for the control-plane chart. |
| oauth.google.clientSecretRef.key | string | `"client-secret"` | Configures `oauth.google.clientSecretRef.key` for the control-plane chart. |
| oauth.google.clientSecretRef.name | string | `""` | Configures `oauth.google.clientSecretRef.name` for the control-plane chart. |
| oauth.google.clientSecretVaultPath | string | `""` | Configures `oauth.google.clientSecretVaultPath` for the control-plane chart. |
| oauth.google.defaultRole | string | `"member"` | Configures `oauth.google.defaultRole` for the control-plane chart. |
| oauth.google.enabled | bool | `false` | Configures `oauth.google.enabled` for the control-plane chart. |
| oauth.google.forceUpdate | bool | `false` | Configures `oauth.google.forceUpdate` for the control-plane chart. |
| oauth.google.groupRoleMappings | object | `{}` | Configures `oauth.google.groupRoleMappings` for the control-plane chart. |
| oauth.google.redirectUri | string | `""` | Configures `oauth.google.redirectUri` for the control-plane chart. |
| oauth.google.requireMfa | bool | `false` | Configures `oauth.google.requireMfa` for the control-plane chart. |
| privacy | object | `{"clickhousePiiTables":["execution_metrics","agent_performance","token_usage"],"dlpEnabled":false,"dsrEnabled":false,"residencyEnforcementEnabled":false}` | Configures `privacy` for the control-plane chart. |
| privacy.clickhousePiiTables | list | `["execution_metrics","agent_performance","token_usage"]` | Configures `privacy.clickhousePiiTables` for the control-plane chart. |
| privacy.dlpEnabled | bool | `false` | Configures `privacy.dlpEnabled` for the control-plane chart. |
| privacy.dsrEnabled | bool | `false` | Configures `privacy.dsrEnabled` for the control-plane chart. |
| privacy.residencyEnforcementEnabled | bool | `false` | Configures `privacy.residencyEnforcementEnabled` for the control-plane chart. |
| scheduler | object | `{"enabled":true,"replicaCount":1}` | Configures `scheduler` for the control-plane chart. |
| scheduler.enabled | bool | `true` | Configures `scheduler.enabled` for the control-plane chart. |
| scheduler.replicaCount | int | `1` | Configures `scheduler.replicaCount` for the control-plane chart. |
| securityCompliance | object | `{"manualEvidenceBucket":"compliance-evidence"}` | Configures `securityCompliance` for the control-plane chart. |
| securityCompliance.manualEvidenceBucket | string | `"compliance-evidence"` | Configures `securityCompliance.manualEvidenceBucket` for the control-plane chart. |
| serviceAccount | object | `{"annotations":{},"create":true,"name":""}` | Configures `serviceAccount` for the control-plane chart. |
| serviceAccount.annotations | object | `{}` | Configures `serviceAccount.annotations` for the control-plane chart. |
| serviceAccount.create | bool | `true` | Configures `serviceAccount.create` for the control-plane chart. |
| serviceAccount.name | string | `""` | Configures `serviceAccount.name` for the control-plane chart. |
| stripe | object | `{"webhookNetworkPolicy":{"enabled":false,"sourceCidrs":[]}}` | are loaded from Vault per rule 39, never from these values. |
| stripe.webhookNetworkPolicy | object | `{"enabled":false,"sourceCidrs":[]}` | https://stripe.com/docs/ips. |
| stripe.webhookNetworkPolicy.enabled | bool | `false` | Configures `stripe.webhookNetworkPolicy.enabled`. |
| stripe.webhookNetworkPolicy.sourceCidrs | list | `[]` | IPv4 source allowlist. Operator-rotated. |
| tenancy | object | `{"cacheTtlSeconds":60,"enforcementLevel":"lenient"}` | Configures hostname tenant resolution for the control-plane chart. |
| tenancy.cacheTtlSeconds | int | `60` | Configures `tenancy.cacheTtlSeconds` for the control-plane chart. |
| tenancy.enforcementLevel | string | `"lenient"` | Configures `tenancy.enforcementLevel` for the control-plane chart. |
| vault | object | `{"addr":"http://musematic-vault.platform-security.svc.cluster.local:8200","approle":{"roleId":"","secretIdSecretRef":""},"authMethod":"kubernetes","caCertSecretRef":"","cache":{"maxStalenessSeconds":300,"ttlSeconds":60},"kubernetes":{"role":"musematic-platform","serviceAccountTokenPath":"/var/run/secrets/tokens/vault-token"},"kvMount":"secret","kvPrefix":"musematic/{environment}","leaseRenewalThreshold":0.5,"mode":"mock","namespace":"","retry":{"attempts":3,"timeoutSeconds":10},"token":""}` | Configures Vault-backed secret resolution for the control-plane chart. |
| vault.addr | string | `"http://musematic-vault.platform-security.svc.cluster.local:8200"` | Configures `vault.addr` for the control-plane chart. |
| vault.approle | object | `{"roleId":"","secretIdSecretRef":""}` | Configures `vault.approle` for the control-plane chart. |
| vault.approle.roleId | string | `""` | Configures `vault.approle.roleId` for the control-plane chart. |
| vault.approle.secretIdSecretRef | string | `""` | Configures `vault.approle.secretIdSecretRef` for the control-plane chart. |
| vault.authMethod | string | `"kubernetes"` | Configures `vault.authMethod` for the control-plane chart. |
| vault.caCertSecretRef | string | `""` | Configures `vault.caCertSecretRef` for the control-plane chart. |
| vault.cache | object | `{"maxStalenessSeconds":300,"ttlSeconds":60}` | Configures `vault.cache` for the control-plane chart. |
| vault.cache.maxStalenessSeconds | int | `300` | Configures `vault.cache.maxStalenessSeconds` for the control-plane chart. |
| vault.cache.ttlSeconds | int | `60` | Configures `vault.cache.ttlSeconds` for the control-plane chart. |
| vault.kubernetes | object | `{"role":"musematic-platform","serviceAccountTokenPath":"/var/run/secrets/tokens/vault-token"}` | Configures `vault.kubernetes` for the control-plane chart. |
| vault.kubernetes.role | string | `"musematic-platform"` | Configures `vault.kubernetes.role` for the control-plane chart. |
| vault.kubernetes.serviceAccountTokenPath | string | `"/var/run/secrets/tokens/vault-token"` | Configures `vault.kubernetes.serviceAccountTokenPath` for the control-plane chart. |
| vault.kvMount | string | `"secret"` | Configures `vault.kvMount` for the control-plane chart. |
| vault.kvPrefix | string | `"musematic/{environment}"` | Configures `vault.kvPrefix` for the control-plane chart. |
| vault.leaseRenewalThreshold | float | `0.5` | Configures `vault.leaseRenewalThreshold` for the control-plane chart. |
| vault.mode | string | `"mock"` | Configures `vault.mode` for the control-plane chart. |
| vault.namespace | string | `""` | Configures `vault.namespace` for the control-plane chart. |
| vault.retry | object | `{"attempts":3,"timeoutSeconds":10}` | Configures `vault.retry` for the control-plane chart. |
| vault.retry.attempts | int | `3` | Configures `vault.retry.attempts` for the control-plane chart. |
| vault.retry.timeoutSeconds | int | `10` | Configures `vault.retry.timeoutSeconds` for the control-plane chart. |
| vault.token | string | `""` | Configures `vault.token` for the control-plane chart. |
| worker | object | `{"enabled":true,"replicaCount":1}` | Configures `worker` for the control-plane chart. |
| worker.enabled | bool | `true` | Configures `worker.enabled` for the control-plane chart. |
| worker.replicaCount | int | `1` | Configures `worker.replicaCount` for the control-plane chart. |
| wsHub | object | `{"enabled":true,"replicaCount":1,"service":{"nodePort":null,"port":8001,"type":"ClusterIP"}}` | Configures `wsHub` for the control-plane chart. |
| wsHub.enabled | bool | `true` | Configures `wsHub.enabled` for the control-plane chart. |
| wsHub.replicaCount | int | `1` | Configures `wsHub.replicaCount` for the control-plane chart. |
| wsHub.service | object | `{"nodePort":null,"port":8001,"type":"ClusterIP"}` | Configures `wsHub.service` for the control-plane chart. |
| wsHub.service.nodePort | string | `nil` | Configures `wsHub.service.nodePort` for the control-plane chart. |
| wsHub.service.port | int | `8001` | Configures `wsHub.service.port` for the control-plane chart. |
| wsHub.service.type | string | `"ClusterIP"` | Configures `wsHub.service.type` for the control-plane chart. |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.13.1](https://github.com/norwoodj/helm-docs/releases/v1.13.1)
