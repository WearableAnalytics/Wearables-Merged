import { createProxyMiddleware, RequestHandler } from 'http-proxy-middleware';
import jwt from 'jsonwebtoken';
import type { IncomingMessage } from 'http';

type JwtProxyConfig = {
  proxyPrefix: string;
  grafanaBaseUrl: string;
  grafanaPathPrefix: string;
  grafanaTlsSkipVerify: boolean;
  grafanaJwtHeader: string;
  grafanaJwtHeaderValuePrefix: string;
  grafanaJwtIssuer: string;
  grafanaJwtAudience: string;
  grafanaJwtTtlSeconds: number;
  grafanaJwtPrivateKey: string;
  grafanaJwtSubject: string;
  grafanaJwtEmail: string;
  grafanaJwtName: string;
  grafanaJwtRole: string;
  grafanaOrgId: string;
  grafanaJwtIatSkewSeconds: number;
  sessionCookieName: string;
  appJwtSecret: string;
};

type HeaderValue = string | string[] | number | undefined;
type SessionJwtPayload = jwt.JwtPayload & {
  userId?: string;
  email?: string;
  name?: string;
  role?: string;
  status?: string;
};
type SessionUser = {
  userId?: string;
  email?: string;
  name?: string;
  role?: string;
};

const stripHeader = (headers: Record<string, string | string[] | undefined>, headerName: string): void => {
  for (const key of Object.keys(headers)) {
    if (key.toLowerCase() === headerName) {
      delete headers[key];
    }
  }
};

const removeFrameAncestors = (headers: Record<string, string | string[] | undefined>): void => {
  const headerKey = Object.keys(headers).find((key) => key.toLowerCase() === 'content-security-policy');
  if (!headerKey) return;

  const rawValue = headers[headerKey];
  const value = Array.isArray(rawValue) ? rawValue.join('; ') : rawValue;
  if (!value) return;

  const directives = value.split(';').map((part) => part.trim()).filter(Boolean);
  const filtered = directives.filter((directive) => !directive.toLowerCase().startsWith('frame-ancestors'));

  if (filtered.length === 0) {
    delete headers[headerKey];
    return;
  }

  headers[headerKey] = filtered.join('; ');
};

const buildProxyPath = (path: string, config: JwtProxyConfig): string => {
  const prefix = config.proxyPrefix || '';
  const stripped = prefix && path.startsWith(prefix) ? path.slice(prefix.length) : path;
  const normalized = stripped.startsWith('/') ? stripped : `/${stripped}`;
  const base = config.grafanaPathPrefix || '';
  const combined = `${base}${normalized}`;
  return combined === '' ? '/' : combined;
};

const redactHeaderValue = (value: HeaderValue): string | string[] => {
  if (Array.isArray(value)) {
    return value.map(() => '[redacted]');
  }
  return '[redacted]';
};

const sanitizeHeaders = (
  headers: Record<string, HeaderValue>,
  extraRedactions: string[],
): Record<string, string | string[]> => {
  const redactions = new Set(
    ['authorization', 'proxy-authorization', 'cookie', 'set-cookie', ...extraRedactions].map((value) =>
      value.toLowerCase(),
    ),
  );
  const sanitized: Record<string, string | string[]> = {};
  for (const [key, value] of Object.entries(headers)) {
    if (value === undefined) continue;
    if (redactions.has(key.toLowerCase())) {
      sanitized[key] = redactHeaderValue(value);
      continue;
    }
    if (Array.isArray(value)) {
      sanitized[key] = value.map((item) => String(item));
    } else {
      sanitized[key] = String(value);
    }
  }
  return sanitized;
};

const resolveTargetUrl = (targetPath: string, baseUrl: string): string => {
  try {
    return new URL(targetPath || '/', baseUrl).toString();
  } catch {
    return `${baseUrl}${targetPath}`;
  }
};

const resolveTargetOrigin = (baseUrl: string): string | null => {
  try {
    return new URL(baseUrl).origin;
  } catch {
    return null;
  }
};

const getRequestPath = (req: IncomingMessage): string => {
  const request = req as IncomingMessage & { originalUrl?: string; url?: string };
  return request.originalUrl ?? request.url ?? '/';
};

const formatJwtHeaderValue = (token: string, config: JwtProxyConfig): string => {
  const explicitPrefix = config.grafanaJwtHeaderValuePrefix.trim();
  const implicitPrefix = config.grafanaJwtHeader.toLowerCase() === 'authorization' ? 'Bearer' : '';
  const prefix = explicitPrefix || implicitPrefix;
  return prefix ? `${prefix} ${token}` : token;
};

const rewriteOriginHeaders = (
  proxyReq: {
    getHeader(name: string): string | string[] | number | undefined;
    setHeader(name: string, value: string): void;
  },
  targetUrl: string,
  baseUrl: string,
): void => {
  const targetOrigin = resolveTargetOrigin(baseUrl);
  if (!targetOrigin) return;

  if (proxyReq.getHeader('origin')) {
    proxyReq.setHeader('origin', targetOrigin);
  }
  if (proxyReq.getHeader('referer')) {
    proxyReq.setHeader('referer', targetUrl);
  }
};

const parseCookies = (cookieHeader?: string): Record<string, string> => {
  if (!cookieHeader) return {};

  return cookieHeader.split(';').reduce<Record<string, string>>((acc, cookiePart) => {
    const [rawName, ...rest] = cookiePart.split('=');
    if (!rawName || rest.length === 0) return acc;
    const name = rawName.trim();
    if (!name) return acc;
    acc[name] = decodeURIComponent(rest.join('='));
    return acc;
  }, {});
};

const parseSessionUser = (cookieHeader: string | undefined, config: JwtProxyConfig): SessionUser | null => {
  if (!config.appJwtSecret) return null;

  const cookies = parseCookies(cookieHeader);
  const token = cookies[config.sessionCookieName];
  if (!token) return null;

  try {
    const decoded = jwt.verify(token, config.appJwtSecret, { algorithms: ['HS256'] }) as SessionJwtPayload;
    if (decoded.status && decoded.status !== 'approved') {
      return null;
    }
    if (!decoded.email && !decoded.userId) {
      return null;
    }
    return {
      userId: decoded.userId,
      email: decoded.email,
      name: decoded.name,
      role: decoded.role,
    };
  } catch {
    return null;
  }
};

const toGrafanaRole = (role?: string): string | undefined => {
  if (!role) return undefined;
  switch (role.toLowerCase()) {
    case 'admin':
      return 'Admin';
    case 'editor':
      return 'Editor';
    case 'grafanaadmin':
      return 'GrafanaAdmin';
    case 'viewer':
    case 'user':
      return 'Viewer';
    default:
      return undefined;
  }
};

const buildJwtPayload = (config: JwtProxyConfig, sessionUser: SessionUser | null): jwt.JwtPayload => {
  const nowSeconds = Math.floor(Date.now() / 1000);
  const skewSeconds = config.grafanaJwtIatSkewSeconds || 0;
  const subject = sessionUser?.email || sessionUser?.userId || config.grafanaJwtSubject;
  if (!subject) {
    throw new Error('No Grafana JWT subject available from session or GRAFANA_JWT_SUBJECT');
  }
  const roleFromSession = toGrafanaRole(sessionUser?.role);
  const payload: jwt.JwtPayload = {
    sub: subject,
    iat: nowSeconds - skewSeconds,
  };
  if (sessionUser?.email || config.grafanaJwtEmail) {
    payload.email = sessionUser?.email || config.grafanaJwtEmail;
  }
  if (sessionUser?.name || config.grafanaJwtName) {
    payload.name = sessionUser?.name || config.grafanaJwtName;
  }
  if (roleFromSession || config.grafanaJwtRole) {
    payload.role = roleFromSession || config.grafanaJwtRole;
  }
  return payload;
};

const signJwt = (config: JwtProxyConfig, sessionUser: SessionUser | null): string => {
  const payload = buildJwtPayload(config, sessionUser);
  return jwt.sign(payload, config.grafanaJwtPrivateKey, {
    algorithm: 'RS256',
    issuer: config.grafanaJwtIssuer,
    audience: config.grafanaJwtAudience,
    expiresIn: config.grafanaJwtTtlSeconds,
  });
};

export const createJwtProxy = (config: JwtProxyConfig): RequestHandler => {
  return createProxyMiddleware({
    target: config.grafanaBaseUrl,
    changeOrigin: true,
    ws: true,
    secure: !config.grafanaTlsSkipVerify,
    pathRewrite: (path) => buildProxyPath(path, config),
    on: {
      proxyReq: (proxyReq, req) => {
        const sessionUser = parseSessionUser(req.headers.cookie, config);
        const token = signJwt(config, sessionUser);
        const jwtHeaderValue = formatJwtHeaderValue(token, config);
        proxyReq.removeHeader('authorization');
        proxyReq.setHeader(config.grafanaJwtHeader, jwtHeaderValue);
        if (config.grafanaJwtHeader.toLowerCase() !== 'authorization') {
          proxyReq.setHeader('authorization', `Bearer ${token}`);
        }
        if (config.grafanaOrgId) {
          proxyReq.setHeader('X-Grafana-Org-Id', config.grafanaOrgId);
        }
        const targetPath = (proxyReq as { path?: string }).path ?? buildProxyPath(getRequestPath(req), config);
        const targetUrl = resolveTargetUrl(targetPath, config.grafanaBaseUrl);
        rewriteOriginHeaders(proxyReq, targetUrl, config.grafanaBaseUrl);
        const headers = sanitizeHeaders(
          proxyReq.getHeaders() as Record<string, HeaderValue>,
          [config.grafanaJwtHeader, 'x-grafana-org-id'],
        );
        const bodyBytes = proxyReq.getHeader('content-length');
        const bodyInfo = bodyBytes ? ` bodyBytes=${bodyBytes}` : '';
        const authSource = sessionUser ? 'session-cookie' : 'static-config';
        // eslint-disable-next-line no-console
        console.log(
          `[Grafana proxy] OUT ${req.method} ${targetUrl}${bodyInfo} authSource=${authSource} headers=${JSON.stringify(headers)}`,
        );
      },
      proxyReqWs: (proxyReq, req) => {
        const sessionUser = parseSessionUser(req.headers.cookie, config);
        const token = signJwt(config, sessionUser);
        const jwtHeaderValue = formatJwtHeaderValue(token, config);
        proxyReq.removeHeader('authorization');
        proxyReq.setHeader(config.grafanaJwtHeader, jwtHeaderValue);
        if (config.grafanaJwtHeader.toLowerCase() !== 'authorization') {
          proxyReq.setHeader('authorization', `Bearer ${token}`);
        }
        if (config.grafanaOrgId) {
          proxyReq.setHeader('X-Grafana-Org-Id', config.grafanaOrgId);
        }
        const targetPath = (proxyReq as { path?: string }).path ?? buildProxyPath(getRequestPath(req), config);
        const targetUrl = resolveTargetUrl(targetPath, config.grafanaBaseUrl);
        rewriteOriginHeaders(proxyReq, targetUrl, config.grafanaBaseUrl);
        const headers = sanitizeHeaders(
          proxyReq.getHeaders() as Record<string, HeaderValue>,
          [config.grafanaJwtHeader, 'x-grafana-org-id'],
        );
        const authSource = sessionUser ? 'session-cookie' : 'static-config';
        // eslint-disable-next-line no-console
        console.log(
          `[Grafana proxy] OUT-WS ${req.method} ${targetUrl} authSource=${authSource} headers=${JSON.stringify(headers)}`,
        );
      },
      proxyRes: (proxyRes, req) => {
        stripHeader(proxyRes.headers as Record<string, string | string[] | undefined>, 'x-frame-options');
        removeFrameAncestors(proxyRes.headers as Record<string, string | string[] | undefined>);
        proxyRes.headers['x-grafana-proxy'] = 'true';
        proxyRes.headers['x-grafana-proxy-target'] = config.grafanaBaseUrl;
        const targetPath = buildProxyPath(getRequestPath(req), config);
        const targetUrl = resolveTargetUrl(targetPath, config.grafanaBaseUrl);
        const headers = sanitizeHeaders(
          proxyRes.headers as Record<string, HeaderValue>,
          ['set-cookie'],
        );
        // eslint-disable-next-line no-console
        console.log(
          `[Grafana proxy] IN ${req.method} ${targetUrl} status=${proxyRes.statusCode} headers=${JSON.stringify(
            headers,
          )}`,
        );
      },
    },
  });
};
