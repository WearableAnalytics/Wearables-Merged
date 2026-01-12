import express from 'express';
import { createServiceAccountProxy } from './serviceAccountProxy.js';
import { serviceAccountConfig } from './serviceAccountConfig.js';

const app = express();
const port = Number(process.env.PORT) || 3002;

app.get('/health', (_req, res) => {
  res.json({ status: 'ok' });
});

if (serviceAccountConfig.serviceAccountToken) {
  const saProxy = createServiceAccountProxy(serviceAccountConfig);
  const saMountPath = serviceAccountConfig.saProxyPrefix || '/grafana';
  app.use(saMountPath, saProxy);
  // eslint-disable-next-line no-console
  console.log(`Service Account proxy will be available at: ${saMountPath}`);
} else {
  // eslint-disable-next-line no-console
  console.warn('Missing GRAFANA_SERVICE_ACCOUNT_TOKEN; proxy is not mounted.');
}

app.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`Grafana proxy listening on http://localhost:${port}`);
});
