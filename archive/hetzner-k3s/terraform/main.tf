terraform {
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.45"
    }
  }
}

provider "hcloud" {
  token = var.hcloud_token
}

# Register each team member's SSH key in Hetzner Cloud so they can access the server
resource "hcloud_ssh_key" "keys" {
  for_each   = var.users
  name       = each.key
  public_key = each.value.ssh_key
}

# Reference SSH keys that already exist in the Hetzner project (optional)
data "hcloud_ssh_key" "existing_keys" {
  for_each = toset(var.existing_ssh_key_names)
  name     = each.value
}

# Cloud firewall – controls inbound traffic at the network edge
# Note: Docker may interfere with local iptables rules, so relying on this is safer
resource "hcloud_firewall" "firewall" {
  name = "${var.server_name}-firewall"

  # Allow SSH from anywhere
  rule {
    direction = "in"
    protocol  = "tcp"
    port      = "22"
    source_ips = [
      "0.0.0.0/0",
      "::/0"
    ]
  }

  # Allow plain HTTP (used for Let's Encrypt challenge / ingress)
  rule {
    direction = "in"
    protocol  = "tcp"
    port      = "80"
    source_ips = [
      "0.0.0.0/0",
      "::/0"
    ]
  }

  # Allow HTTPS traffic
  rule {
    direction = "in"
    protocol  = "tcp"
    port      = "443"
    source_ips = [
      "0.0.0.0/0",
      "::/0"
    ]
  }

  # Allow K3s API server access (needed for kubectl from outside)
  rule {
    direction = "in"
    protocol  = "tcp"
    port      = "6443"
    source_ips = [
      "0.0.0.0/0",
      "::/0"
    ]
  }
}

# Single K3s server (single-node setup)
# For multi-node, see infra/README.md – Upgrading to Multi-Node
resource "hcloud_server" "server" {
  name        = var.server_name
  server_type = var.server_type
  location    = var.location
  image       = "ubuntu-24.04"

  # Attach all SSH keys (both newly registered and pre-existing)
  ssh_keys = concat(
    [for key in hcloud_ssh_key.keys : key.id],
    [for key in data.hcloud_ssh_key.existing_keys : key.id]
  )

  firewall_ids = [hcloud_firewall.firewall.id]

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  labels = {
    managed_by  = "terraform"
    environment = "production"
  }
}
