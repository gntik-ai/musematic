path "secret/data/musematic/{{ env }}/tenants/{{ tenant_slug }}/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/metadata/musematic/{{ env }}/tenants/{{ tenant_slug }}/*" {
  capabilities = ["read", "list"]
}

path "secret/data/musematic/{{ env }}/_platform/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/musematic/{{ env }}/_platform/*" {
  capabilities = ["read", "list"]
}
