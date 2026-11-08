# Extraction Service Helm Chart

## Configuration

This chart creates a Secret for configuration values. Update `values.yaml`:

```yaml
env:
  DB_LORD_BASE_URL: "http://db-lord.db-lord.svc.cluster.local:8080"
```

The pod also reads the Secret `extraction-service-auth` (`authSecretRef`), which holds
`EXTRACTION_INTERNAL_JWT_SECRET`. It must match the BFF's and is created for both by
`scripts/bootstrap-runtime-secrets.sh`. The pod does not start until it exists.

## Accessing the Service

Within the cluster:

```
http://extraction-service.extraction-service.svc.cluster.local:8010
```

## Deploy

```bash
helm template extraction-service ./gitops/apps/services/extraction-service --namespace extraction-service -s templates/extraction-service-secrets.yaml > extraction-service-secrets.yaml
helm upgrade extraction-service ./gitops/apps/services/extraction-service --namespace extraction-service --install --create-namespace
```
