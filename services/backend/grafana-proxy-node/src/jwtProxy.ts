import { createProxyMiddleware, RequestHandler } from 'http-proxy-middleware';
import jwt from 'jsonwebtoken';

type JwtProxyConfig = {
  proxyPrefix: string;
  grafanaBaseUrl: string;
  grafanaPathPrefix: string;
  grafanaTlsSkipVerify: boolean;
  grafanaJwtHeader: string;
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
};

type HeaderValue = string | string[] | number | undefined;

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

const buildJwtPayload = (config: JwtProxyConfig): jwt.JwtPayload => {
  const nowSeconds = Math.floor(Date.now() / 1000);
  const skewSeconds = config.grafanaJwtIatSkewSeconds || 0;
  const payload: jwt.JwtPayload = {
    sub: config.grafanaJwtSubject,
    iat: nowSeconds - skewSeconds,
  };
  if (config.grafanaJwtEmail) {
    payload.email = config.grafanaJwtEmail;
  }
  if (config.grafanaJwtName) {
    payload.name = config.grafanaJwtName;
  }
  if (config.grafanaJwtRole) {
    payload.role = config.grafanaJwtRole;
  }
  return payload;
};

const signJwt = (config: JwtProxyConfig): string => {
  const payload = buildJwtPayload(config);
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
        const token = signJwt(config);
        proxyReq.setHeader(config.grafanaJwtHeader, token);
        proxyReq.removeHeader('authorization');
        if (config.grafanaOrgId) {
          proxyReq.setHeader('X-Grafana-Org-Id', config.grafanaOrgId);
        }
        const targetPath = (proxyReq as { path?: string }).path ?? buildProxyPath(req.originalUrl, config);
        const targetUrl = resolveTargetUrl(targetPath, config.grafanaBaseUrl);
        const headers = sanitizeHeaders(
          proxyReq.getHeaders() as Record<string, HeaderValue>,
          [config.grafanaJwtHeader, 'x-grafana-org-id'],
        );
        const bodyBytes = proxyReq.getHeader('content-length');
        const bodyInfo = bodyBytes ? ` bodyBytes=${bodyBytes}` : '';
        // eslint-disable-next-line no-console
        console.log(
          `[Grafana proxy] OUT ${req.method} ${targetUrl}${bodyInfo} headers=${JSON.stringify(headers)}`,
        );
      },
      proxyReqWs: (proxyReq, req) => {
        const token = signJwt(config);
        proxyReq.setHeader(config.grafanaJwtHeader, token);
        proxyReq.removeHeader('authorization');
        if (config.grafanaOrgId) {
          proxyReq.setHeader('X-Grafana-Org-Id', config.grafanaOrgId);
        }
        const targetPath = (proxyReq as { path?: string }).path ?? buildProxyPath(req.originalUrl, config);
        const targetUrl = resolveTargetUrl(targetPath, config.grafanaBaseUrl);
        const headers = sanitizeHeaders(
          proxyReq.getHeaders() as Record<string, HeaderValue>,
          [config.grafanaJwtHeader, 'x-grafana-org-id'],
        );
        // eslint-disable-next-line no-console
        console.log(
          `[Grafana proxy] OUT-WS ${req.method} ${targetUrl} headers=${JSON.stringify(headers)}`,
        );
      },
      proxyRes: (proxyRes, req) => {
        stripHeader(proxyRes.headers as Record<string, string | string[] | undefined>, 'x-frame-options');
        removeFrameAncestors(proxyRes.headers as Record<string, string | string[] | undefined>);
        proxyRes.headers['x-grafana-proxy'] = 'true';
        proxyRes.headers['x-grafana-proxy-target'] = config.grafanaBaseUrl;
        const targetPath = buildProxyPath(req.originalUrl, config);
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
