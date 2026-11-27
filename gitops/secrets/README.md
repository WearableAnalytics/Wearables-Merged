# Runtime Secrets

The Kubernetes Secrets that the charts in `gitops/apps` reference but never create. This chart deploys them; Argo CD runs it as the application `secrets` (`prune: false`).

| Directory | Used by | Content |
|---|---|---|
| `prod/<namespace>/<name>.yaml` | production (`values.yaml`) | SealedSecrets, encrypted with `sealed-secrets-cert.pem`; the Sealed Secrets controller decrypts them |
| `local/<namespace>/<name>.yaml` | local minikube (`values-local.yaml`) | Dev Secrets: plain Secrets with dev-only values |

The file name is the Secret name, the directory its namespace.

The full guide (adding and changing secrets, Shared Values, the Sealing Key) follows with the migration of the production secrets.
