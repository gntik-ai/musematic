variable "zone_name" {
  description = "Apex DNS zone name (e.g. musematic.ai). Required when create_zone=true."
  type        = string
}

variable "create_zone" {
  description = "Whether this module call creates the zone resource. Production sets true; dev shares the prod zone via zone_id and sets false."
  type        = bool
  default     = true
}

variable "zone_id" {
  description = "Pre-existing Hetzner DNS zone id. Required when create_zone=false (dev calls)."
  type        = string
  default     = ""
}

variable "subtree" {
  description = "Optional subtree prefix for bootstrap records. Empty creates apex/app/api/grafana under the zone root; \"dev\" creates dev/app.dev/dev.api/dev.grafana."
  type        = string
  default     = ""
}

variable "lb_ipv4" {
  description = "Public IPv4 of the cluster's Hetzner Cloud Load Balancer."
  type        = string
}

variable "lb_ipv6" {
  description = "Public IPv6 of the cluster's Hetzner Cloud Load Balancer. Empty disables AAAA records."
  type        = string
  default     = ""
}

variable "cloudflare_pages_ipv4" {
  description = "Optional IPv4 for the status page bootstrap A record (set when status is hosted on Cloudflare Pages — rule 49 outage independence)."
  type        = string
  default     = ""
}
