terraform {
  required_version = ">= 1.6"

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.50"
    }
    hetznerdns = {
      source  = "timohirt/hetznerdns"
      version = "~> 2.2"
    }
  }
}

provider "hcloud" {}
provider "hetznerdns" {}

module "cluster" {
  source = "../../modules/hetzner-cluster"

  cluster_name              = var.cluster_name
  control_plane_count       = var.control_plane_count
  worker_count              = var.worker_count
  control_plane_server_type = var.control_plane_server_type
  worker_server_type        = var.worker_server_type
  location                  = var.location
  network_zone              = var.network_zone
  firewall_allowed_cidrs    = var.firewall_allowed_cidrs
  load_balancer_type        = var.load_balancer_type # UPD-053 (106): default lb21 in variables.tf
  ssh_public_key_file       = var.ssh_public_key_file
}

# UPD-053 (106) — DNS zone module owns the apex zone (musematic.ai) and the
# bootstrap apex/app/api/grafana/status A+AAAA records. The wildcard "*"
# record is intentionally NOT created here; per-tenant subdomains are
# managed by the application-side DnsAutomationClient
# (apps/control-plane/src/platform/tenants/dns_automation.py).
module "dns" {
  source = "../../modules/hetzner-dns-zone"

  zone_name             = "musematic.ai"
  subtree               = ""
  lb_ipv4               = module.cluster.lb_ipv4
  lb_ipv6               = module.cluster.lb_ipv6
  cloudflare_pages_ipv4 = var.cloudflare_pages_ipv4
}

output "lb_ipv4" {
  description = "Public IPv4 of the production cluster's Hetzner Cloud LB."
  value       = module.cluster.lb_ipv4
}

output "lb_ipv6" {
  description = "Public IPv6 of the production cluster's Hetzner Cloud LB."
  value       = module.cluster.lb_ipv6
}

output "zone_id" {
  description = "Hetzner DNS zone id for musematic.ai. Populates HETZNER_DNS_ZONE_ID in the Helm values."
  value       = module.dns.zone_id
}
