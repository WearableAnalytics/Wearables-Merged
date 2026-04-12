# Hetzner Infrastructure – K3s Cluster

## Quick Start (Single-Node)

### Prerequisites
- [Terraform](https://developer.hashicorp.com/terraform/downloads) >= 1.5
- [Ansible](https://docs.ansible.com/ansible/latest/installation_guide/) >= 2.14
- Hetzner Cloud API token ([Cloud Console → Project → API Tokens](https://console.hetzner.cloud/))

### 1. Configuration
```bash
cp infra/terraform/terraform.tvars.example infra/terraform/terraform.tfvars
vim infra/terraform/terraform.tfvars
# Fill in HCLOUD_TOKEN and SSH keys for EACH team member!
```

### 2. One-Click Deploy
```bash
make deploy
```

Steps:
1. `terraform apply` – provisions the Hetzner server
2. `gen-inventory.py` – builds the Ansible inventory from the Terraform output IP
3. `ansible-playbook` – hardens the server, installs K3s, saves kubeconfig locally

### 3. Test the Cluster
```bash
make nodes
# or
KUBECONFIG=infra/kubeconfig.yaml kubectl get nodes
```

### Useful Commands
| Command | Description |
|---|---|
| `make deploy` | Full deployment (Terraform + Ansible) |
| `make destroy` | Delete all Hetzner resources |
| `make tf-output` | Show Hetzner IPs |
| `make inventory` | Regenerate inventory (e.g. after IP change) |
| `make ansible` | Re-run Ansible only (server already exists) |
| `make nodes` | Show cluster nodes |
| `make status` | Show all pods |

---

## Upgrading to Multi-Node

### Overview of Changes

#### 1. Extend Terraform (`infra/terraform/main.tf`)

Instead of a single server, create a private network, a master node, and N worker nodes:

```hcl
# Private network for intra-cluster communication
resource "hcloud_network" "cluster_net" {
  name     = "${var.server_name}-net"
  ip_range = "10.0.0.0/16"
}

resource "hcloud_network_subnet" "cluster_subnet" {
  network_id   = hcloud_network.cluster_net.id
  type         = "cloud"
  network_zone = "eu-central"
  ip_range     = "10.0.1.0/24"
}

# Master node
resource "hcloud_server" "master" {
  name        = "${var.server_name}-master"
  server_type = var.server_type
  location    = var.location
  image       = "ubuntu-24.04"
  ssh_keys    = [for key in hcloud_ssh_key.keys : key.id]
  firewall_ids = [hcloud_firewall.firewall.id]
  public_net { ipv4_enabled = true; ipv6_enabled = false }
}

resource "hcloud_server_network" "master_net" {
  server_id  = hcloud_server.master.id
  network_id = hcloud_network.cluster_net.id
  ip         = "10.0.1.10"
}

# Worker nodes
resource "hcloud_server" "workers" {
  count       = var.worker_count
  name        = "${var.server_name}-worker-${count.index + 1}"
  server_type = var.worker_type
  location    = var.location
  image       = "ubuntu-24.04"
  ssh_keys    = [for key in hcloud_ssh_key.keys : key.id]
  firewall_ids = [hcloud_firewall.firewall.id]
  public_net { ipv4_enabled = true; ipv6_enabled = false }
}

resource "hcloud_server_network" "worker_nets" {
  count      = var.worker_count
  server_id  = hcloud_server.workers[count.index].id
  network_id = hcloud_network.cluster_net.id
  ip         = "10.0.1.${20 + count.index}"
}
```

Add to `variables.tf`:
```hcl
variable "worker_count" {
  type    = number
  default = 2
}

variable "worker_type" {
  type    = string
  default = "cx21"
}
```

Replace `outputs.tf` with:
```hcl
output "master_public_ip"  { value = hcloud_server.master.ipv4_address }
output "master_private_ip" { value = "10.0.1.10" }
output "worker_public_ips"  { value = [for w in hcloud_server.workers : w.ipv4_address] }
output "worker_private_ips" { value = [for i in range(var.worker_count) : "10.0.1.${20 + i}"] }
```

#### 2. Switch `gen-inventory.py` to Multi-Node

Update `infra/gen-inventory.py` to read the new Terraform outputs:

```python
master_public_ip  = data["master_public_ip"]["value"]
master_private_ip = data["master_private_ip"]["value"]
worker_public_ips  = data["worker_public_ips"]["value"]
worker_private_ips = data["worker_private_ips"]["value"]

lines = [
    "all:",
    "  vars:",
    f"    ansible_user: {ANSIBLE_USER}",
    "    ansible_python_interpreter: /usr/bin/python3",
    "  children:",
    "    k3s_master:",
    "      hosts:",
    "        master:",
    f"          ansible_host: {master_public_ip}",
    f"          k3s_master_public_ip: {master_public_ip}",
    f"          k3s_master_private_ip: {master_private_ip}",
    f"          k3s_flannel_iface: eth1",
    "    k3s_workers:",
    "      hosts:",
]
for i, (pub, priv) in enumerate(zip(worker_public_ips, worker_private_ips), start=1):
    lines += [
        f"        worker-{i}:",
        f"          ansible_host: {pub}",
        f"          k3s_master_private_ip: {master_private_ip}",
        f"          k3s_flannel_iface: eth1",
    ]
```

#### 3. Split the Playbook into Master / Worker Playbooks (`playbook.yml`)

```yaml
- name: Set up master node
  hosts: k3s_master
  become: yes
  vars:
    k3s_version: "v1.28.5+k3s1"
  roles:
    - base
    - users
    - security
    - k3s_server   # roles/k3s_server – already implemented

- name: Set up worker nodes
  hosts: k3s_workers
  become: yes
  vars:
    k3s_version: "v1.28.5+k3s1"
  roles:
    - base
    - users
    - security
    - k3s_agent    # roles/k3s_agent – already implemented
```

> The roles `roles/k3s_server` and `roles/k3s_agent` are already implemented and ready to use.

#### 4. Add Flannel VXLAN Firewall Rule

Append to the firewall resource in `main.tf` (only needed if you expose the private network to Hetzner's cloud firewall):
```hcl
# Flannel VXLAN – intra-cluster overlay traffic
rule {
  direction  = "in"
  protocol   = "udp"
  port       = "8472"
  source_ips = ["10.0.1.0/24"]
}
```
