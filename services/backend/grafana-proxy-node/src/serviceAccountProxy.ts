import { createProxyMiddleware, RequestHandler } from 'http-proxy-middleware';

type ServiceAccountConfig = {
  grafanaBaseUrl: string;
  serviceAccountToken: string;
  grafanaPathPrefix: string;
  saProxyPrefix: string;
  grafanaTlsSkipVerify: boolean;
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
  });
};
