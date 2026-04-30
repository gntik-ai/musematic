# ChannelConfig.signing_secret_ref and OutboundWebhook.signing_secret_ref reads.
path "secret/data/musematic/+/notifications/webhook-secrets/*" {
  capabilities = ["read", "list"]
}

path "secret/data/musematic/+/notifications/sms-providers/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/musematic/+/notifications/webhook-secrets/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/musematic/+/notifications/sms-providers/*" {
  capabilities = ["read", "list"]
}
