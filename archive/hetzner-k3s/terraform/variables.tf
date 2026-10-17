variable "hcloud_token" {
  description = "Hetzner Cloud API token – generate in the Hetzner Cloud Console under Project → API Tokens"
  type        = string
  sensitive   = true
}

variable "server_name" {
  description = "Display name of the server in Hetzner Cloud"
  type        = string
  default     = "k3s-server"
}

variable "server_type" {
  description = "Hetzner server type (e.g. cx21 = 2 vCPU / 4 GB RAM, cx31 = 2 vCPU / 8 GB)"
  type        = string
  default     = "cx21"
}

variable "location" {
  description = "Hetzner datacenter location (nbg1 = Nuremberg, fsn1 = Falkenstein, hel1 = Helsinki)"
  type        = string
  default     = "nbg1"
}

variable "users" {
  description = "Map of user names to SSH public keys and sudo flag – each key is registered in Hetzner and added to the server"
  type = map(object({
    ssh_key = string
    sudo    = bool
  }))
}

variable "existing_ssh_key_names" {
  description = "Names of SSH keys already uploaded to the Hetzner project that should also be added to the server (optional)"
  type        = list(string)
  default     = []
}
