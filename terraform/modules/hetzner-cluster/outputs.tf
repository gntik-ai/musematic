output "load_balancer_ipv4" {
  description = "Ingress load balancer IPv4 address."
  value       = hcloud_load_balancer.ingress.ipv4
}

output "load_balancer_ipv6" {
  description = "Ingress load balancer IPv6 address."
  value       = hcloud_load_balancer.ingress.ipv6
}

output "control_plane_ipv4" {
  description = "Control-plane public IPv4 addresses."
  value       = hcloud_server.control_plane[*].ipv4_address
}

output "worker_ipv4" {
  description = "Worker public IPv4 addresses."
  value       = hcloud_server.worker[*].ipv4_address
}

output "kubeconfig_path" {
  description = "Suggested kubeconfig output path for the kubeadm bootstrap guide."
  value       = "${path.root}/kubeconfig"
}

# UPD-053 (106) — short-name aliases consumed by the hetzner-dns-zone module
# wiring in terraform/environments/{production,dev}/main.tf. The longer
# names above are kept for backwards compatibility with operator scripts.
output "lb_ipv4" {
  description = "Alias for `load_balancer_ipv4` — consumed by the hetzner-dns-zone module."
  value       = hcloud_load_balancer.ingress.ipv4
}

output "lb_ipv6" {
  description = "Alias for `load_balancer_ipv6` — consumed by the hetzner-dns-zone module."
  value       = hcloud_load_balancer.ingress.ipv6
}

output "network_id" {
  description = "Hetzner private network id; used by additional services attaching to the same network."
  value       = hcloud_network.cluster.id
}
