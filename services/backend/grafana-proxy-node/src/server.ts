import express from 'express';
import { createJwtProxy } from './jwtProxy.js';
import { config } from './config.js';

const app = express();
const port = config.port;

app.get('/health', (_req, res) => {
  res.json({ status: 'ok' });
});

if (config.grafanaJwtPrivateKey && config.grafanaJwtSubject) {
  const jwtProxy = createJwtProxy(config);
  const mountPath = config.proxyPrefix || '/grafana';
  app.use(mountPath, (req, _res, next) => {
    // eslint-disable-next-line no-console
    console.log(`[Grafana proxy] incoming ${req.method} ${req.originalUrl}`);
    next();
  });
  app.use(mountPath, jwtProxy);
  // eslint-disable-next-line no-console
  console.log(`JWT proxy will be available at: ${mountPath}`);
  // eslint-disable-next-line no-console
  console.log(
    `Grafana target: ${config.grafanaBaseUrl}${config.grafanaPathPrefix || ''}`,
  );
  // eslint-disable-next-line no-console
  console.log(`Grafana TLS verify: ${config.grafanaTlsSkipVerify ? 'disabled' : 'enabled'}`);
  // eslint-disable-next-line no-console
  console.log(`Grafana JWT header: ${config.grafanaJwtHeader}`);
  // eslint-disable-next-line no-console
  console.log(`Grafana JWT subject: ${config.grafanaJwtSubject}`);
} else {
  // eslint-disable-next-line no-console
  console.warn('Missing GRAFANA_JWT_PRIVATE_KEY or GRAFANA_JWT_SUBJECT; proxy is not mounted.');
}

app.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`Grafana proxy listening on http://localhost:${port}`);
});
