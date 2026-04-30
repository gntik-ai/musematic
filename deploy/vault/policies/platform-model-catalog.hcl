# ModelProviderCredential.vault_ref reads.
path "secret/data/musematic/+/model-providers/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/musematic/+/model-providers/*" {
  capabilities = ["read", "list"]
}
