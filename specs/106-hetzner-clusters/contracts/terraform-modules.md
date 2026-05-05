# Contract — Terraform module shape

## Existing modules (extended)

### `terraform/modules/hetzner-cluster/`

EXTEND `outputs.tf` (currently absent — file is new under this module):

```hcl
output "lb_ipv4" {
  description = "Public IPv4 address of the cluster's Cloud LB. Consumed by hetzner-dns-zone for apex/app/api/grafana A records."
  value       = hcloud_load_balancer.ingress.ipv4
}

output "lb_ipv6" {
  description = "Public IPv6 address of the cluster's Cloud LB."
  value       = hcloud_load_balancer.ingress.ipv6
}

output "kubeconfig" {
  description = "Path on the operator's workstation where the kubeconfig for this cluster is written."
  value       = local_file.kubeconfig.filename
  sensitive   = true
}
```

EXTEND `variables.tf` to add an explicit per-env default expectation (no module-level default; the env overlay sets it):

```hcl
variable "load_balancer_type" {
  description = "Hetzner Cloud LB type. Production overlays set lb21; dev overlays set lb11."
  type        = string
  # No default — must be set in environments/{env}/main.tf
}
```

The existing resources in `main.tf` are unchanged.

## NEW module

### `terraform/modules/hetzner-dns-zone/`

A small module owning the DNS zone and the bootstrap records (the application-managed per-tenant records remain owned by `dns_automation.py`, NOT by Terraform).

```text
terraform/modules/hetzner-dns-zone/
├── main.tf
├── variables.tf
└── outputs.tf
```

`main.tf`:

```hcl
terraform {
  required_version = ">= 1.6"
  required_providers {
    hetznerdns = {
      source  = "timohirt/hetznerdns"
      version = "~> 2.2"
    }
  }
}

resource "hetznerdns_zone" "primary" {
  name = var.zone_name
  ttl  = 300
}

# Apex + app + api + grafana + status — all point at the cluster's LB.
locals {
  bootstrap_a_records = {
    "@"       = var.lb_ipv4   # apex
    "app"     = var.lb_ipv4
    "api"     = var.lb_ipv4
    "grafana" = var.lb_ipv4
    "status"  = var.cloudflare_pages_ipv4   # external — Cloudflare Pages CNAME flattening
  }
  bootstrap_aaaa_records = {
    "@"       = var.lb_ipv6
    "app"     = var.lb_ipv6
    "api"     = var.lb_ipv6
    "grafana" = var.lb_ipv6
    # status: AAAA via Cloudflare; not duplicated here.
  }
}

resource "hetznerdns_record" "bootstrap_a" {
  for_each = local.bootstrap_a_records
  zone_id  = hetznerdns_zone.primary.id
  name     = each.key
  type     = "A"
  value    = each.value
  ttl      = 300
}

resource "hetznerdns_record" "bootstrap_aaaa" {
  for_each = local.bootstrap_aaaa_records
  zone_id  = hetznerdns_zone.primary.id
  name     = each.key
  type     = "AAAA"
  value    = each.value
  ttl      = 300
}

# The wildcard "*" is intentionally NOT created here.
# Per-tenant records are managed by the application
# (apps/control-plane/src/platform/tenants/dns_automation.py).
```

`variables.tf`:

```hcl
variable "zone_name" {
  description = "Apex DNS zone name (e.g. musematic.ai). For dev, the prod zone is shared and dev records live under the dev.* subtree, so dev's hetzner-dns-zone module call uses zone_name = musematic.ai but creates dev.app, dev.api, dev.grafana, dev.status records via a different bootstrap_a_records map (set in environments/dev/main.tf)."
  type        = string
}

variable "lb_ipv4" {
  description = "IPv4 address of the cluster's Cloud LB. Consumed from hetzner-cluster.outputs.lb_ipv4."
  type        = string
}

variable "lb_ipv6" {
  description = "IPv6 address of the cluster's Cloud LB."
  type        = string
}

variable "cloudflare_pages_ipv4" {
  description = "IPv4 of the Cloudflare Pages project hosting status.musematic.ai. Pre-provisioned out-of-band."
  type        = string
  default     = ""
}
```

`outputs.tf`:

```hcl
output "zone_id" {
  description = "Hetzner DNS zone id; consumed by the Helm chart's hetzner.dns.zone setting and by tenants/dns_automation.py at startup."
  value       = hetznerdns_zone.primary.id
}
```

## Environment overlays

### `terraform/environments/production/main.tf` (extended)

```hcl
provider "hcloud" {}
provider "hetznerdns" {}

module "cluster" {
  source                    = "../../modules/hetzner-cluster"
  cluster_name              = var.cluster_name
  control_plane_count       = var.control_plane_count
  worker_count              = var.worker_count
  control_plane_server_type = "ccx33"             # default for prod
  worker_server_type        = "ccx53"             # default for prod
  load_balancer_type        = "lb21"              # NEW — explicit per-env
  location                  = var.location
  network_zone              = var.network_zone
  firewall_allowed_cidrs    = var.firewall_allowed_cidrs
  ssh_public_key_file       = var.ssh_public_key_file
}

module "dns" {                                     # NEW
  source                = "../../modules/hetzner-dns-zone"
  zone_name             = "musematic.ai"
  lb_ipv4               = module.cluster.lb_ipv4
  lb_ipv6               = module.cluster.lb_ipv6
  cloudflare_pages_ipv4 = var.cloudflare_pages_ipv4
}

output "lb_ipv4"  { value = module.cluster.lb_ipv4  }
output "lb_ipv6"  { value = module.cluster.lb_ipv6  }
output "zone_id"  { value = module.dns.zone_id      }
```

### `terraform/environments/dev/main.tf` (extended)

```hcl
provider "hcloud" {}
provider "hetznerdns" {}

module "cluster" {
  source                    = "../../modules/hetzner-cluster"
  cluster_name              = var.cluster_name
  control_plane_count       = 1
  worker_count              = 1
  control_plane_server_type = "ccx21"             # default for dev
  worker_server_type        = "ccx21"             # default for dev
  load_balancer_type        = "lb11"              # NEW — explicit per-env
  location                  = var.location
  network_zone              = var.network_zone
  firewall_allowed_cidrs    = var.firewall_allowed_cidrs
  ssh_public_key_file       = var.ssh_public_key_file
}

# Dev shares the prod zone — it doesn't create the apex.
# It does create the dev.* subtree records pointing at the dev LB.
resource "hetznerdns_record" "dev_a" {
  for_each = {
    "dev"          = module.cluster.lb_ipv4   # dev.musematic.ai apex
    "app.dev"      = module.cluster.lb_ipv4
    "dev.api"      = module.cluster.lb_ipv4
    "api.dev"      = module.cluster.lb_ipv4
    "dev.grafana"  = module.cluster.lb_ipv4
    "status.dev"   = var.cloudflare_pages_dev_ipv4  # if dev uses Cloudflare Pages too; else point at cluster
  }
  zone_id = var.shared_zone_id   # prod zone id, fed via -var
  name    = each.key
  type    = "A"
  value   = each.value
  ttl     = 300
}

# AAAA equivalents omitted for brevity; same pattern.

output "lb_ipv4" { value = module.cluster.lb_ipv4 }
output "lb_ipv6" { value = module.cluster.lb_ipv6 }
```

`terraform.tfvars.example` for both environments documents the variable values with placeholders only — operators copy to `terraform.tfvars` and fill secrets locally; the `.tfvars` file is gitignored.

## CI integration

The existing CI is in `.github/workflows/ci.yml`. UPD-053 adds a `terraform-validate` job (gated by paths-filter on `terraform/**`) that runs `terraform fmt -check`, `terraform init -backend=false`, and `terraform validate` for both env overlays. No `terraform plan` against real Hetzner accounts in CI (would require credentials and racy state). Runbooks in `docs/operations/hetzner-cluster-provisioning.md` walk operators through `terraform apply` on their workstation.
