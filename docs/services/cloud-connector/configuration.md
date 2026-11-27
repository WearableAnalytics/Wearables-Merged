# Configuration & Local Development

## Configuration

All environment variables are listed in `services/backend/cloud-connector/.env.example`, `app/config.py`, and the Helm chart (`gitops/apps/services/cloud-connector/values.yaml`):

- `PUBLIC_BASE_URL` and `OAUTH_REDIRECT_URI`: Base URL and OAuth callback (for example `http://localhost/cloud/callback` locally or `https://wearables.charite.de/cloud/callback` in the cluster)
- `JWT_SECRET` and `JWT_ISSUER`: Must match `wearables-bff` for JWT-protected routes
- `CLOUD_CONNECTOR_STORAGE_PATH`: Path to persistent JSON connection store (default `/data/connections.json`)
- `KAFKA_BOOTSTRAP_SERVERS` and `KAFKA_TOPIC`: Target Kafka broker and raw topic (`wearables-raw`)

## Local Development & Tests

```bash
cd services/backend/cloud-connector
cp .env.example .env

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pytest -q tests/
```

For local webhook testing, it is recommended to set up a `cloudflared` tunnel to expose the local webhook endpoint to the internet.
