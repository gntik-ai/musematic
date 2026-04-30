# Cost-governance model-provider price/account credential reads.
path "secret/data/musematic/+/model-providers/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/musematic/+/model-providers/*" {
  capabilities = ["read", "list"]
}
