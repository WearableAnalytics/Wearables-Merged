# Registration Service Node Helm Chart

## Secrets Management

The chart creates a Secret resource for sensitive configuration. Edit the secret template at `templates/registration-service-node-secret.yaml` to add your secrets:

```yaml
stringData:
  JWT_SECRET: "your-jwt-secret-here"
  DATABASE_URL: "postgresql://user:pass@host:5432/db"
```

## API Endpoints

The service exposes the following mock endpoints:

- `GET    {API_PREFIX}/health`
- `GET    {API_PREFIX}/charite/cases/:cCaseId`
- `GET    {API_PREFIX}/patients`
- `GET    {API_PREFIX}/patients/:patientId`
- `GET    {API_PREFIX}/patients/:patientId/cases`
- `GET    {API_PREFIX}/cases`
- `GET    {API_PREFIX}/cases/:caseId`
- `POST   {API_PREFIX}/cases/from-charite-case`
- `POST   {API_PREFIX}/cases/verify-token`

## Accessing the Service

### Within the Cluster

Other services can access the registration-service-node using:

```
http://registration-service-node.registration-service-node.svc.cluster.local:3001
```

### Port Forwarding (Development)

For local development and testing:

```bash
kubectl port-forward -n registration-service-node \
  svc/registration-service-node 3001:3001
```

Then access the service at `http://localhost:3001/api/health`

## Deploy

helm template registration-service-node ./gitops/apps/services/registration-service-node --namespace registration-service-node -s templates/registration-service-node-secret.yaml > registration-service-node-secret.yaml

helm upgrade registration-service-node ./gitops/apps/services/registration-service-node --namespace registration-service-node --install
