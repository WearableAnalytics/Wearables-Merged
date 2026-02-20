import express from 'express';
import jwt from 'jsonwebtoken';
import { createJwtProxy, getSessionUserFromCookie } from './jwtProxy.js';
import { config } from './config.js';

const app = express();
const port = config.port;
const DEFAULT_FROM = 'now-24h';
const DEFAULT_TO = 'now';
const MAX_DEVICE_ID_LENGTH = 1024;

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

const toGrafanaDashboardIdValue = (value: unknown): string | null => {
  const candidate = queryValue(value);
  if (!candidate) return null;
  return /^[A-Za-z0-9_-]+$/.test(candidate) ? candidate : null;
};

const toGrafanaThemeValue = (value: unknown): 'light' | 'dark' => {
  const candidate = queryValue(value)?.toLowerCase();
  return candidate === 'dark' ? 'dark' : 'light';
};

const toGrafanaTimeValue = (value: unknown, defaultValue: string): string => {
  const candidate = queryValue(value);
  if (!candidate) return defaultValue;

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

  return defaultValue;
};

type CaseTokenPayload = {
  caseId: string;
  patientId: string;
  type: 'case-verification';
};

const normalizeOpaqueDeviceId = (value: string): string | null => {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (trimmed.length > MAX_DEVICE_ID_LENGTH) return null;
  if (/\s/.test(trimmed)) return null;
  return trimmed;
};

const resolveDeviceId = (rawDeviceId: string): string | null => {
  try {
    const decoded = jwt.verify(rawDeviceId, config.appJwtSecret, {
      algorithms: ['HS256'],
      issuer: config.appJwtIssuer,
    }) as unknown as CaseTokenPayload;

    if (decoded.type !== 'case-verification') {
      return null;
    }

    const resolved = decoded.patientId?.trim();
    if (!resolved) {
      return null;
    }
    console.log(
      '[Grafana proxy] resolved deviceId from case token',
      JSON.stringify({
        tokenSubject: decoded.caseId,
        patientId: resolved,
      }),
    );
    return resolved;
  } catch {
    // Fallback for deployments where case/device identifiers are opaque strings.
  }

  const opaqueDeviceId = normalizeOpaqueDeviceId(rawDeviceId);
  if (!opaqueDeviceId) return null;
  console.log(
    '[Grafana proxy] using raw deviceId from embed parameter',
    JSON.stringify({ length: opaqueDeviceId.length }),
  );
  return opaqueDeviceId;
};

app.get('/health', (_req, res) => {
  res.json({ status: 'ok' });
});

if (config.grafanaBaseUrl && config.grafanaJwtPrivateKey && config.appJwtSecret) {
  const jwtProxy = createJwtProxy(config);
  const mountPath = config.proxyPrefix || '/grafana-proxy';
  const embedPath = toPath(mountPath, '/embed');
  const allowedDashboardIds = new Set(
    config.grafanaAllowedDashboardIds.filter((dashboardId) => /^[A-Za-z0-9_-]+$/.test(dashboardId)),
  );

  app.get(embedPath, (req, res) => {
    const sessionUser = getSessionUserFromCookie(req.headers.cookie, config);
    if (!sessionUser) {
      res.status(401).json({ error: 'Missing or invalid session' });
      return;
    }

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

    const resolvedDeviceId = resolveDeviceId(rawDeviceId);
    if (!resolvedDeviceId) {
      res.status(400).json({ error: 'deviceId must be a non-empty identifier without whitespace' });
      return;
    }

    let from = toGrafanaTimeValue(req.query.from, DEFAULT_FROM);
    const to = toGrafanaTimeValue(req.query.to, DEFAULT_TO);
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
      'var-deviceId': resolvedDeviceId,
      '_dash.hideTimePicker': 'true',
      '_dash.hideVariables': 'true',
      '_dash.hideLinks': 'true',
    });
    const dashboardPath = toPath(
      mountPath,
      `/d/${encodeURIComponent(dashboardId)}/${encodeURIComponent(dashboardId)}`,
    );

    // Full kiosk mode is enforced by presence of the `kiosk` flag.
    const redirectUrl = `${dashboardPath}?${params.toString()}&kiosk`;
    res.setHeader('Cache-Control', 'no-store');
    res.redirect(302, redirectUrl);
  });

  app.use(mountPath, (req, res, next) => {
    const sessionUser = getSessionUserFromCookie(req.headers.cookie, config);
    if (!sessionUser) {
      res.status(401).json({ error: 'Missing or invalid session' });
      return;
    }
    next();
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
  console.log(`Grafana embed endpoint: ${embedPath}`);
} else {
  // eslint-disable-next-line no-console
  console.warn(
    'Missing GRAFANA_BASE_URL, GRAFANA_JWT_PRIVATE_KEY, and/or APP_JWT_SECRET; proxy is not mounted.',
  );
}

app.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`Grafana proxy listening on http://localhost:${port}`);
});
