# Audit-chain signing material reads and rotation writes.
path "secret/data/musematic/+/audit-chain/*" {
  capabilities = ["read", "list", "update"]
}

path "secret/metadata/musematic/+/audit-chain/*" {
  capabilities = ["read", "list", "update"]
}

path "secret/data/musematic/+/_internal/connectivity-test/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/metadata/musematic/+/_internal/connectivity-test/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "transit/sign/audit-chain" {
  capabilities = ["update"]
}
