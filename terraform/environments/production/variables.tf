variable "cluster_name" {
  type    = string
  default = "musematic-prod"
}

variable "control_plane_count" {
  type    = number
  default = 1
}

variable "worker_count" {
  type    = number
  default = 3
}

variable "control_plane_server_type" {
  type    = string
  default = "ccx33"
}

variable "worker_server_type" {
  type    = string
  default = "ccx53"
}

variable "location" {
  type    = string
  default = "fsn1"
}

variable "network_zone" {
  type    = string
  default = "eu-central"
}

variable "firewall_allowed_cidrs" {
  type = list(string)
}

variable "load_balancer_type" {
  description = "UPD-053 (106) — Hetzner Cloud Load Balancer type. Production defaults to lb21 (5x10 TB / 200 Mbps) per the spec's US1 sizing."
  type        = string
  default     = "lb21"
}

variable "ssh_public_key_file" {
  type = string
}

# UPD-053 (106) — Cloudflare Pages IPv4 used as the A-record value for
# `status.musematic.ai` (constitutional rule 49 — status independence).
# Cloudflare Pages itself sits behind Cloudflare's anycast network; this
# variable accepts the IPv4 the operator's Pages project advertises after
# the custom-domain wizard. Empty disables the bootstrap A record (operator
# uses a CNAME instead via the Hetzner DNS UI).
variable "cloudflare_pages_ipv4" {
  description = "IPv4 of the Cloudflare Pages project hosting status.musematic.ai. Provisioned out-of-band; left empty disables the bootstrap A record."
  type        = string
  default     = ""
}
