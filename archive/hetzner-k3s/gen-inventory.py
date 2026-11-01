#!/usr/bin/env python3
"""
gen-inventory.py – Generates an Ansible inventory from `terraform output -json`.

Usage:
    cd infra/terraform && terraform output -json | python3 ../gen-inventory.py

Or via Makefile:
    make inventory

Single-node mode (current):
    Reads the `server_ip` output and writes a single-host inventory.

Multi-node mode (see infra/README.md – Upgrading to Multi-Node):
    Update this script to read master_public_ip, master_private_ip,
    worker_public_ips, and worker_private_ips once Terraform is extended.
"""

import json
import sys


ANSIBLE_USER = "root"


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Error parsing terraform output: {e}", file=sys.stderr)
        sys.exit(1)

    # Pull the public IPv4 address Terraform assigned to the server
    server_ip = data["server_ip"]["value"]

    lines = [
        "all:",
        "  hosts:",
        "    k3s_server:",
        f"      ansible_host: {server_ip}",   # IP comes directly from Terraform output
        f"      ansible_user: {ANSIBLE_USER}",
        "      ansible_become: yes",
        "      ansible_become_method: sudo",
        "  vars:",
        "    ansible_python_interpreter: /usr/bin/python3",
    ]

    print("\n".join(lines))


if __name__ == "__main__":
    main()