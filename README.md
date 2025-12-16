# Wearables Platform Monorepo

Unified repository for the Wearables clinical analytics platform.

## Repository Structure

- **ci-cd/**: GitHub Actions workflows and deployment scripts
- **docs/**: Architecture docs, runbooks, ADRs
- **gitops/**: Kubernetes manifests and Helm charts (GitOps-ready)
- **infra/**: Infrastructure as Code (Terraform, Ansible)
- **observability/**: Dashboards, alerts, monitoring configs
- **packages/**: Shared libraries, such as registration api definition
- **services/**: Application services (backend & mobile)

## Migration Notice

This repository was created by merging multiple repositories while preserving Git history.
See `docs/migration/MIGRATION_SUMMARY.md` for details and links to archived repositories.

