output "zone_id" {
  description = "Hetzner DNS zone id; consumed by the platform Helm values (HETZNER_DNS_ZONE_ID env var) and by tenants/dns_automation.py at startup."
  value       = local.effective_zone_id
}

output "bootstrap_record_count" {
  description = "Total number of bootstrap A+AAAA records this module manages."
  value       = length(hetznerdns_record.a) + length(hetznerdns_record.aaaa)
}
