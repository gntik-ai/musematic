terraform {
  required_version = ">= 1.6"

  required_providers {
    hetznerdns = {
      source  = "timohirt/hetznerdns"
      version = "~> 2.2"
    }
  }
}

# UPD-053 (106) — Hetzner DNS zone + bootstrap records.
#
# The apex zone is owned by the production env's invocation of this module;
# dev shares the same zone (operates on the dev.* subtree). The `subtree`
# variable controls the prefix applied to bootstrap record names:
#   subtree=""    → "@", "app", "api", "grafana", "status"
#   subtree="dev" → "dev", "app.dev", "dev.api", "dev.grafana", "status.dev"
#
# The wildcard "*" is intentionally NOT created here — per-tenant subdomains
# are owned by the application-side DnsAutomationClient.

resource "hetznerdns_zone" "primary" {
  count = var.create_zone ? 1 : 0

  name = var.zone_name
  ttl  = 300
}

locals {
  effective_zone_id = var.create_zone ? hetznerdns_zone.primary[0].id : var.zone_id

  # Map of bootstrap record name → IPv4 value. The "@" / apex case is the zone root.
  apex_a = var.subtree == "" ? {
    "@"       = var.lb_ipv4
    "app"     = var.lb_ipv4
    "api"     = var.lb_ipv4
    "grafana" = var.lb_ipv4
  } : {}

  apex_aaaa = var.subtree == "" ? {
    "@"       = var.lb_ipv6
    "app"     = var.lb_ipv6
    "api"     = var.lb_ipv6
    "grafana" = var.lb_ipv6
  } : {}

  subtree_a = var.subtree != "" ? {
    "${var.subtree}"         = var.lb_ipv4
    "app.${var.subtree}"     = var.lb_ipv4
    "${var.subtree}.api"     = var.lb_ipv4
    "api.${var.subtree}"     = var.lb_ipv4
    "${var.subtree}.grafana" = var.lb_ipv4
  } : {}

  subtree_aaaa = var.subtree != "" ? {
    "${var.subtree}"         = var.lb_ipv6
    "app.${var.subtree}"     = var.lb_ipv6
    "${var.subtree}.api"     = var.lb_ipv6
    "api.${var.subtree}"     = var.lb_ipv6
    "${var.subtree}.grafana" = var.lb_ipv6
  } : {}

  status_a = var.cloudflare_pages_ipv4 != "" ? (
    var.subtree == ""
    ? { "status" = var.cloudflare_pages_ipv4 }
    : { "status.${var.subtree}" = var.cloudflare_pages_ipv4 }
  ) : {}
}

resource "hetznerdns_record" "a" {
  for_each = merge(local.apex_a, local.subtree_a, local.status_a)

  zone_id = local.effective_zone_id
  name    = each.key
  type    = "A"
  value   = each.value
  ttl     = 300
}

resource "hetznerdns_record" "aaaa" {
  for_each = merge(local.apex_aaaa, local.subtree_aaaa)

  zone_id = local.effective_zone_id
  name    = each.key
  type    = "AAAA"
  value   = each.value
  ttl     = 300
}
