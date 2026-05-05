variable "cluster_name" {
  type    = string
  default = "musematic-dev"
}

variable "control_plane_count" {
  type    = number
  default = 1
}

variable "worker_count" {
  type    = number
  default = 2
}

variable "control_plane_server_type" {
  description = "UPD-053 (106) — dev defaults to ccx21 per the spec's US2 sizing."
  type        = string
  default     = "ccx21"
}

variable "worker_server_type" {
  description = "UPD-053 (106) — dev defaults to ccx21."
  type        = string
  default     = "ccx21"
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
  description = "UPD-053 (106) — dev defaults to lb11."
  type        = string
  default     = "lb11"
}

variable "ssh_public_key_file" {
  type = string
}

# UPD-053 (106) — Dev shares the prod DNS zone (musematic.ai). The prod
# environment's `terraform output zone_id` provides this; pass via
#   terraform apply -var="shared_zone_id=$(terraform -chdir=../production output -raw zone_id)" \
#                   -var-file=terraform.tfvars
# Empty disables the dev.* bootstrap records (operator manages manually).
variable "shared_zone_id" {
  description = "Hetzner DNS zone id for musematic.ai (the prod-owned apex zone). Required when this env applies the dev.* subtree records."
  type        = string
  default     = ""
}

variable "cloudflare_pages_dev_ipv4" {
  description = "Optional IPv4 for status.dev.musematic.ai. Empty disables the bootstrap A record (dev runs the in-cluster status deployment)."
  type        = string
  default     = ""
}
