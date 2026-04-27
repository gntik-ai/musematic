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
  type    = string
  default = "cax11"
}

variable "worker_server_type" {
  type    = string
  default = "cax11"
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
  type    = string
  default = "lb11"
}

variable "ssh_public_key_file" {
  type = string
}
