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

# Register SSH keys in Hetzner Cloud
resource "hcloud_ssh_key" "keys" {
  for_each   = var.users
  name       = each.key
  public_key = each.value.ssh_key
}

# Reference existing SSH keys by name
data "hcloud_ssh_key" "existing_keys" {
  for_each = toset(var.existing_ssh_key_names)
  name     = each.value
}

# Firewall (even if docker fucks up IPTables ;)
resource "hcloud_firewall" "firewall" {
  name = "${var.server_name}-firewall"

  # SSH
  rule {
    direction = "in"
    protocol  = "tcp"
    port      = "22"
    source_ips = [
      "0.0.0.0/0",
      "::/0"
    ]
  }

  # HTTP
  rule {
    direction = "in"
    protocol  = "tcp"
    port      = "80"
    source_ips = [
      "0.0.0.0/0",
      "::/0"
    ]
  }

  # HTTPS
  rule {
    direction = "in"
    protocol  = "tcp"
    port      = "443"
    source_ips = [
      "0.0.0.0/0",
      "::/0"
    ]
  }

  # K3s API
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

# Create Hetzner Cloud Server
resource "hcloud_server" "server" {
  name        = var.server_name
  server_type = var.server_type
  location    = var.location
  image       = "ubuntu-24.04"
  
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
    managed_by = "terraform"
    environment = "production"
  }
}