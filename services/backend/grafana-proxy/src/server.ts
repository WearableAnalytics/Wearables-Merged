import express from 'express';
import jwt from 'jsonwebtoken';
import { createJwtProxy } from './jwtProxy.js';
import { config } from './config.js';

const app = express();
const port = config.port;
const DEFAULT_FROM = 'now-24h';
const DEFAULT_TO = 'now';

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

const toGrafanaPanelValue = (value: unknown): string | null => {
  const candidate = queryValue(value);
  if (!candidate) return null;
  return /^[A-Za-z0-9_-]+$/.test(candidate) ? candidate : null;
};

const toGrafanaDashboardIdValue = (value: unknown): string | null => {
  const candidate = queryValue(value);
  if (!candidate) return null;
  return /^[A-Za-z0-9_-]+$/.test(candidate) ? candidate : null;
};

const toGrafanaThemeValue = (value: unknown): 'light' | 'dark' => {
  const candidate = queryValue(value)?.toLowerCase();
  return candidate === 'dark' ? 'dark' : 'light';
};

const toGrafanaTimeValue = (value: unknown, fallback: string): string => {
  const candidate = queryValue(value);
  if (!candidate) return fallback;

  if (/^\d{10,13}$/.test(candidate)) {
    return candidate;
  }
  if (/^now(?:[-+]\d+[smhdwMy])?$/.test(candidate)) {
    return candidate;
  }

  const parsed = Date.parse(candidate);
  if (!Number.isNaN(parsed)) {
    return String(parsed);
  }

  return fallback;
};

type CaseTokenPayload = {
  caseId: string;
  patientId: string;
  type: 'case-verification';
};

const resolveDeviceIdFromToken = (rawDeviceId: string | null): string | null => {
  if (!rawDeviceId) return null;
  if (!config.appJwtSecret) return rawDeviceId;

  try {
    const decoded = jwt.verify(rawDeviceId, config.appJwtSecret, {
      issuer: 'registration-service',
    }) as CaseTokenPayload;

    if (decoded.type !== 'case-verification') {
      return rawDeviceId;
    }

    const resolved = decoded.patientId || rawDeviceId;
    console.log(
      '[Grafana proxy] resolved deviceId from case token',
      JSON.stringify({
        tokenSubject: decoded.caseId,
        patientId: resolved,
      }),
    );
    return resolved;
  } catch {
    return rawDeviceId;
  }
};

app.get('/health', (_req, res) => {
  res.json({ status: 'ok' });
});

if (config.grafanaBaseUrl && config.grafanaJwtPrivateKey && (config.grafanaJwtSubject || config.appJwtSecret)) {
  const jwtProxy = createJwtProxy(config);
  const mountPath = config.proxyPrefix || '/grafana';
  const embedPath = toPath(mountPath, '/embed');
  const allowedDashboardIds = new Set(
    config.grafanaAllowedDashboardIds.filter((dashboardId) => /^[A-Za-z0-9_-]+$/.test(dashboardId)),
  );

  app.get(embedPath, (req, res) => {
    const rawDeviceId = queryValue(req.query.deviceId);
    if (!rawDeviceId) {
      res.status(400).json({ error: 'Missing required query parameter: deviceId' });
      return;
    }
    if (allowedDashboardIds.size === 0 || !config.grafanaDashboardDatasource) {
      res.status(500).json({
        error: 'Proxy is missing GRAFANA_ALLOWED_DASHBOARD_IDS and/or GRAFANA_DASHBOARD_DATASOURCE configuration',
      });
      return;
    }

    const deviceId = resolveDeviceIdFromToken(rawDeviceId);

    let from = toGrafanaTimeValue(req.query.from, DEFAULT_FROM);
    const to = toGrafanaTimeValue(req.query.to, DEFAULT_TO);
    const viewPanel = toGrafanaPanelValue(req.query.viewPanel);
    const theme = toGrafanaThemeValue(req.query.theme);
    const dashboardId = toGrafanaDashboardIdValue(req.query.dashboardUid);
    if (!dashboardId) {
      res.status(400).json({ error: 'Missing required query parameter: dashboardUid' });
      return;
    }
    if (!allowedDashboardIds.has(dashboardId)) {
      res.status(400).json({
        error: 'Unsupported dashboardUid. Configure GRAFANA_ALLOWED_DASHBOARD_IDS to allow this dashboard.',
      });
      return;
    }
    if (/^\d+$/.test(from) && /^\d+$/.test(to) && Number(from) >= Number(to)) {
      from = DEFAULT_FROM;
    }

    const params = new URLSearchParams({
      orgId: config.grafanaOrgId || '1',
      from,
      to,
      theme,
      timezone: 'browser',
      'var-DS_INFLUXDB': config.grafanaDashboardDatasource,
      'var-deviceId': deviceId,
      '_dash.hideTimePicker': 'true',
      '_dash.hideVariables': 'true',
      '_dash.hideLinks': 'true',
    });
    if (viewPanel) {
      params.set('viewPanel', viewPanel);
      params.set('__feature.dashboardSceneSolo', 'true');
    }

    const dashboardPath = toPath(
      mountPath,
      `/d/${encodeURIComponent(dashboardId)}/${encodeURIComponent(dashboardId)}`,
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

    const isAllowedDashboardPath = Array.from(allowedDashboardIds).some((dashboardId) => {
      const dashboardPath = `/d/${encodeURIComponent(dashboardId)}`;
      return req.path === dashboardPath || req.path.startsWith(`${dashboardPath}/`);
    });
    if (isAllowedDashboardPath) {
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
