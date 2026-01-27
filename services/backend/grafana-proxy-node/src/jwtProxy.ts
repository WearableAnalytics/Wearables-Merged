import { createProxyMiddleware, RequestHandler } from 'http-proxy-middleware';
import jwt from 'jsonwebtoken';

type JwtProxyConfig = {
  proxyPrefix: string;
  grafanaBaseUrl: string;
  grafanaPathPrefix: string;
  grafanaTlsSkipVerify: boolean;
  grafanaJwtHeader: string;
  grafanaJwtKeyId: string;
  grafanaJwtIssuer: string;
  grafanaJwtAudience: string;
  grafanaJwtTtlSeconds: number;
  grafanaJwtPrivateKey: string;
  grafanaJwtSubject: string;
  grafanaJwtEmail: string;
  grafanaJwtName: string;
  grafanaJwtRole: string;
  grafanaOrgId: string;
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

const buildJwtPayload = (config: JwtProxyConfig): jwt.JwtPayload => {
  const payload: jwt.JwtPayload = {
    sub: config.grafanaJwtSubject,
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
    keyid: config.grafanaJwtKeyId,
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
    onProxyReq: (proxyReq, req) => {
      const token = signJwt(config);
      proxyReq.setHeader(config.grafanaJwtHeader, token);
      proxyReq.removeHeader('authorization');
      if (config.grafanaOrgId) {
        proxyReq.setHeader('X-Grafana-Org-Id', config.grafanaOrgId);
      }
      const targetPath = (proxyReq as { path?: string }).path ?? '';
      // eslint-disable-next-line no-console
      console.log(`[Grafana proxy] ${req.method} ${req.originalUrl} -> ${config.grafanaBaseUrl}${targetPath}`);
    },
    onProxyReqWs: (proxyReq, req) => {
      const token = signJwt(config);
      proxyReq.setHeader(config.grafanaJwtHeader, token);
      proxyReq.removeHeader('authorization');
      if (config.grafanaOrgId) {
        proxyReq.setHeader('X-Grafana-Org-Id', config.grafanaOrgId);
      }
      const targetPath = (proxyReq as { path?: string }).path ?? '';
      // eslint-disable-next-line no-console
      console.log(`[Grafana proxy] WS ${req.method} ${req.originalUrl} -> ${config.grafanaBaseUrl}${targetPath}`);
    },
    onProxyRes: (proxyRes, req) => {
      stripHeader(proxyRes.headers as Record<string, string | string[] | undefined>, 'x-frame-options');
      removeFrameAncestors(proxyRes.headers as Record<string, string | string[] | undefined>);
      proxyRes.headers['x-grafana-proxy'] = 'true';
      proxyRes.headers['x-grafana-proxy-target'] = config.grafanaBaseUrl;
      // eslint-disable-next-line no-console
      console.log(`[Grafana proxy] ${req.method} ${req.originalUrl} <- ${proxyRes.statusCode}`);
    },
  });
};
