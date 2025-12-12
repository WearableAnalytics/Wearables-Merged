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
See `docs/migration/MIGRATION_SUMMARY.md` for details and links to archived repositories.

# wearables_app

A new Flutter project.

## Getting Started

This project is a starting point for a Flutter application.

A few resources to get you started if this is your first Flutter project:

- [Lab: Write your first Flutter app](https://docs.flutter.dev/get-started/codelab)
- [Cookbook: Useful Flutter samples](https://docs.flutter.dev/cookbook)

For help getting started with Flutter development, view the
[online documentation](https://docs.flutter.dev/), which offers tutorials,
samples, guidance on mobile development, and a full API reference.


To test background fetch in the iOS simulator, run the following command in terminal:
```
e -l objc -- (void)[[BGTaskScheduler sharedScheduler] _simulateLaunchForTaskWithIdentifier:@"com.transistorsoft.fetch"]
```
