# OAuthProvider.client_secret_ref reads and rotation writes, plus IBORConnector.credential_ref reads.
path "secret/data/musematic/+/oauth/*" {
  capabilities = ["create", "read", "update", "list"]
}

path "secret/data/musematic/+/ibor/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/musematic/+/oauth/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/musematic/+/ibor/*" {
  capabilities = ["read", "list"]
}
