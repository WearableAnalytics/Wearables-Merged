import { createProxyMiddleware, RequestHandler } from 'http-proxy-middleware';

type ServiceAccountConfig = {
  grafanaBaseUrl: string;
  serviceAccountToken: string;
  grafanaPathPrefix: string;
  saProxyPrefix: string;
  grafanaTlsSkipVerify: boolean;
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

const buildProxyPath = (path: string, config: ServiceAccountConfig): string => {
  const prefix = config.saProxyPrefix || '';
  const stripped = prefix && path.startsWith(prefix) ? path.slice(prefix.length) : path;
  const normalized = stripped.startsWith('/') ? stripped : `/${stripped}`;
  const base = config.grafanaPathPrefix || '';
  const combined = `${base}${normalized}`;
  return combined === '' ? '/' : combined;
};

export const createServiceAccountProxy = (config: ServiceAccountConfig): RequestHandler => {
  return createProxyMiddleware({
    target: config.grafanaBaseUrl,
    changeOrigin: true,
    ws: true,
    secure: !config.grafanaTlsSkipVerify,
    pathRewrite: (path) => buildProxyPath(path, config),
    onProxyReq: (proxyReq) => {
      proxyReq.setHeader('Authorization', `Bearer ${config.serviceAccountToken}`);
    },
    onProxyReqWs: (proxyReq) => {
      proxyReq.setHeader('Authorization', `Bearer ${config.serviceAccountToken}`);
    },
    onProxyRes: (proxyRes) => {
      stripHeader(proxyRes.headers as Record<string, string | string[] | undefined>, 'x-frame-options');
      removeFrameAncestors(proxyRes.headers as Record<string, string | string[] | undefined>);
    },
  });
};
