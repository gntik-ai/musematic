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
  load_balancer_type        = var.load_balancer_type
  ssh_public_key_file       = var.ssh_public_key_file
}

# UPD-053 (106) — Dev shares the prod DNS zone (musematic.ai); this module
# call does NOT create the zone (create_zone=false) and operates only on
# the dev.* subtree. The shared_zone_id is fed via -var from the prod env's
# `terraform output zone_id`.
module "dns" {
  count  = var.shared_zone_id != "" ? 1 : 0
  source = "../../modules/hetzner-dns-zone"

  create_zone           = false
  zone_id               = var.shared_zone_id
  zone_name             = "musematic.ai"
  subtree               = "dev"
  lb_ipv4               = module.cluster.lb_ipv4
  lb_ipv6               = module.cluster.lb_ipv6
  cloudflare_pages_ipv4 = var.cloudflare_pages_dev_ipv4
}

output "lb_ipv4" {
  description = "Public IPv4 of the dev cluster's Hetzner Cloud LB."
  value       = module.cluster.lb_ipv4
}

output "lb_ipv6" {
  description = "Public IPv6 of the dev cluster's Hetzner Cloud LB."
  value       = module.cluster.lb_ipv6
}
