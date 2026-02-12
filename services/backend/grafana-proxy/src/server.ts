import express from 'express';
import { createJwtProxy } from './jwtProxy.js';
import { config } from './config.js';

const app = express();
const port = config.port;
const DASHBOARD_SLUG = 'wearables-dashboard-real';

const toPath = (prefix: string, suffix: string): string => `${prefix}${suffix}` || '/';
const acceptsHtml = (value: string | string[] | undefined): boolean => {
  if (typeof value === 'string') return value.includes('text/html');
  if (Array.isArray(value)) return value.some((part) => part.includes('text/html'));
  return false;
};

const queryValue = (value: unknown): string | null => {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
  }
  if (Array.isArray(value) && typeof value[0] === 'string') {
    const trimmed = value[0].trim();
    return trimmed.length > 0 ? trimmed : null;
  }
  return null;
};

app.get('/health', (_req, res) => {
  res.json({ status: 'ok' });
});

if (config.grafanaBaseUrl && config.grafanaJwtPrivateKey && (config.grafanaJwtSubject || config.appJwtSecret)) {
  const jwtProxy = createJwtProxy(config);
  const mountPath = config.proxyPrefix || '/grafana';
  const embedPath = toPath(mountPath, '/embed');

  app.get(embedPath, (req, res) => {
    const deviceId = queryValue(req.query.deviceId);
    if (!deviceId) {
      res.status(400).json({ error: 'Missing required query parameter: deviceId' });
      return;
    }
    if (!config.grafanaDashboardId || !config.grafanaDashboardDatasource) {
      res.status(500).json({
        error: 'Proxy is missing GRAFANA_DASHBOARD_ID and/or GRAFANA_DASHBOARD_DATASOURCE configuration',
      });
      return;
    }

    const params = new URLSearchParams({
      orgId: config.grafanaOrgId || '1',
      from: 'now-7d',
      to: 'now',
      timezone: 'browser',
      'var-DS_INFLUXDB': config.grafanaDashboardDatasource,
      'var-deviceId': deviceId,
      '_dash.hideTimePicker': 'true',
      '_dash.hideVariables': 'true',
      '_dash.hideLinks': 'true',
    });

    const dashboardPath = toPath(
      mountPath,
      `/d/${encodeURIComponent(config.grafanaDashboardId)}/${encodeURIComponent(DASHBOARD_SLUG)}`,
    );

    // Full kiosk mode is enforced by presence of the `kiosk` flag.
    const redirectUrl = `${dashboardPath}?${params.toString()}&kiosk`;
    res.setHeader('Cache-Control', 'no-store');
    res.redirect(302, redirectUrl);
  });

  app.use(mountPath, (req, _res, next) => {
    // eslint-disable-next-line no-console
    console.log(`[Grafana proxy] incoming ${req.method} ${req.originalUrl}`);
    next();
  });
  app.use(mountPath, (req, res, next) => {
    if (!acceptsHtml(req.headers.accept)) {
      next();
      return;
    }

    const allowedDashboardPath = `/d/${encodeURIComponent(config.grafanaDashboardId)}`;
    if (req.path === allowedDashboardPath || req.path.startsWith(`${allowedDashboardPath}/`)) {
      next();
      return;
    }

    // Block Grafana app-shell navigation to home/dashboards/explore/etc.
    res.status(403).send('Forbidden');
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
  // eslint-disable-next-line no-console
  console.log(`Grafana embed endpoint: ${embedPath}`);
} else {
  // eslint-disable-next-line no-console
  console.warn(
    'Missing GRAFANA_BASE_URL, GRAFANA_JWT_PRIVATE_KEY, and/or both GRAFANA_JWT_SUBJECT + APP_JWT_SECRET; proxy is not mounted.',
  );
}

app.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`Grafana proxy listening on http://localhost:${port}`);
});
