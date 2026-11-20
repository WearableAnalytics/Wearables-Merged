# Extraction Service Helm Chart

## Configuration

Plain settings are in `config` in `values.yaml`:

```yaml
config:
  DB_LORD_BASE_URL: "http://db-lord.db-lord.svc.cluster.local:8080"
```

The chart does not create its Secret. Provision `extraction-service-secrets`
(`secretRef`) outside Git with `DB_LORD_OPERATOR_TOKEN`, the same value as
db-lord's `LEGACY_OPERATOR_TOKEN`.

## Accessing the Service

Within the cluster:

```
http://extraction-service.extraction-service.svc.cluster.local:8010
```

## Deploy

```bash
helm upgrade extraction-service ./gitops/apps/services/extraction-service --namespace extraction-service --install --create-namespace
```
