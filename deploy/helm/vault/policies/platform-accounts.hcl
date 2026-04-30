# Minimal account-scoped future secret reads.
path "secret/data/musematic/+/accounts/*" {
  capabilities = ["read"]
}

path "secret/metadata/musematic/+/accounts/*" {
  capabilities = ["read", "list"]
}
