# Wearables Platform Monorepo

Unified repository for the Wearables clinical analytics platform.

## Repository Structure

- **gitops/**: Kubernetes manifests and Helm charts (GitOps-ready)
- **infra/**: Infrastructure as Code (Terraform, Ansible)
- **services/**: Application services (backend & mobile)
- **observability/**: Dashboards, alerts, monitoring configs
- **ci-cd/**: GitHub Actions workflows and deployment scripts
- **docs/**: Architecture docs, runbooks, ADRs

## Migration Notice

This repository was created by merging multiple repositories while preserving Git history.
See `docs/migration/` for details and links to archived repositories.

