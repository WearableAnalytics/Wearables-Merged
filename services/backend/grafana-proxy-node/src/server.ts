import express, { NextFunction, Request, Response } from 'express';
import jwt from 'jsonwebtoken';
import { createProxyMiddleware } from 'http-proxy-middleware';
import type { JwtPayload } from './config.js';
import { config } from './config.js';

type AuthedRequest = Request & {
  user?: JwtPayload;
  grafanaJwt?: string;
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

const getUserFromRequest = (req: Request): JwtPayload | undefined => {
  try {
    const cookies = parseCookies(req.headers.cookie);
    const token = cookies[config.sessionCookieName];
    if (!token) return undefined;

    const decoded = jwt.verify(token, config.appJwtSecret, {
      algorithms: ['HS256'],
    }) as JwtPayload;

    if (!decoded.userId || !decoded.email) {
      throw new Error('Invalid session token payload');
    }

    return decoded;
  } catch (err) {
    return undefined;
  }
};

const issueGrafanaJwt = (user: JwtPayload): string => {
  return jwt.sign(
    {
      sub: user.userId,
      email: user.email,
      name: user.name,
      role: config.grafanaDefaultRole,
    },
    config.grafanaJwtPrivateKey,
    {
      algorithm: 'RS256',
      keyid: config.grafanaJwtKeyId,
      issuer: config.grafanaJwtIssuer,
      audience: config.grafanaJwtAudience,
      expiresIn: config.grafanaJwtTtlSeconds,
    },
  );
};

const authRequired = (req: AuthedRequest, res: Response, next: NextFunction): void => {
  const user = getUserFromRequest(req);
  if (!user) {
    res.status(401).json({ error: 'Authentication required' });
    return;
  }
  req.user = user;
  req.grafanaJwt = issueGrafanaJwt(user);
  next();
};

const buildProxyPath = (path: string): string => {
  const prefix = config.proxyPrefix || '';
  const stripped = prefix && path.startsWith(prefix) ? path.slice(prefix.length) : path;
  const normalized = stripped.startsWith('/') ? stripped : `/${stripped}`;
  const base = config.grafanaPathPrefix || '';
  const combined = `${base}${normalized}`;
  return combined === '' ? '/' : combined;
};

const app = express();

app.get('/health', (_req, res) => {
  res.json({ status: 'ok' });
});

app.get('/.well-known/jwks.json', (_req, res) => {
  res.json({ keys: [config.grafanaPublicJwk] });
});

const proxy = createProxyMiddleware({
  target: config.grafanaBaseUrl,
  changeOrigin: true,
  ws: true,
  secure: !config.grafanaTlsSkipVerify,
  pathRewrite: buildProxyPath,
  onProxyReq: (proxyReq, req) => {
    const authedReq = req as AuthedRequest;
    if (authedReq.grafanaJwt) {
      proxyReq.setHeader(config.grafanaJwtHeader, authedReq.grafanaJwt);
    }
    if (config.grafanaOrgId) {
      proxyReq.setHeader('X-Grafana-Org-Id', config.grafanaOrgId);
    }
  },
  onProxyReqWs: (proxyReq, req) => {
    const authedReq = req as AuthedRequest;
    if (authedReq.grafanaJwt) {
      proxyReq.setHeader(config.grafanaJwtHeader, authedReq.grafanaJwt);
    }
    if (config.grafanaOrgId) {
      proxyReq.setHeader('X-Grafana-Org-Id', config.grafanaOrgId);
    }
  },
});

const proxyMountPath = config.proxyPrefix || '/';
app.use(proxyMountPath, authRequired, proxy);

app.listen(config.port, () => {
  // eslint-disable-next-line no-console
  console.log(`Grafana proxy listening on http://localhost:${config.port}${config.proxyPrefix || '/'}`);
});
