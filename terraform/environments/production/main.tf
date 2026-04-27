terraform {
  required_version = ">= 1.6"

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.50"
    }
  }
}

provider "hcloud" {}

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
