# Runtime connector credential reads during execution.
path "secret/data/musematic/+/connectors/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/musematic/+/connectors/*" {
  capabilities = ["read", "list"]
}
