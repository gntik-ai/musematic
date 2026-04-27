variable "cluster_name" {
  type        = string
  description = "Cluster name used for resource names and labels."
}

variable "control_plane_count" {
  type        = number
  description = "Number of control-plane nodes."
  default     = 1
}

variable "worker_count" {
  type        = number
  description = "Number of worker nodes."
  default     = 3
}

variable "control_plane_server_type" {
  type        = string
  description = "Hetzner server type for control-plane nodes."
  default     = "ccx33"
}

variable "worker_server_type" {
  type        = string
  description = "Hetzner server type for worker nodes."
  default     = "ccx53"
}

variable "location" {
  type        = string
  description = "Hetzner location."
  default     = "fsn1"
}

variable "network_zone" {
  type        = string
  description = "Hetzner private network zone."
  default     = "eu-central"
}

variable "network_cidr" {
  type        = string
  description = "Private network CIDR."
  default     = "10.10.0.0/16"
}

variable "subnet_cidr" {
  type        = string
  description = "Private subnet CIDR."
  default     = "10.10.1.0/24"
}

variable "firewall_allowed_cidrs" {
  type        = list(string)
  description = "CIDRs allowed to reach SSH and Kubernetes API."
}

variable "load_balancer_type" {
  type        = string
  description = "Hetzner load balancer type."
  default     = "lb11"
}

variable "ssh_public_key_file" {
  type        = string
  description = "Path to the operator SSH public key."
}

variable "server_image" {
  type        = string
  description = "Server image."
  default     = "ubuntu-22.04"
}
