import 'dotenv/config';
import { readFileSync } from 'fs';
import { createPublicKey } from 'crypto';

type JwtPayload = {
  userId: string;
  email: string;
  name?: string;
};

const normalizePrefix = (value: string): string => {
  const trimmed = value.trim();
  if (!trimmed || trimmed === '/') return '';
  const withSlash = trimmed.startsWith('/') ? trimmed : `/${trimmed}`;
  return withSlash.endsWith('/') ? withSlash.slice(0, -1) : withSlash;
};

const readPrivateKey = (): string => {
  if (process.env.GRAFANA_JWT_PRIVATE_KEY) {
    return process.env.GRAFANA_JWT_PRIVATE_KEY.replace(/\\n/g, '\n');
  }
  if (process.env.GRAFANA_JWT_PRIVATE_KEY_PATH) {
    return readFileSync(process.env.GRAFANA_JWT_PRIVATE_KEY_PATH, 'utf8');
  }
  throw new Error('Missing GRAFANA_JWT_PRIVATE_KEY or GRAFANA_JWT_PRIVATE_KEY_PATH');
};

const grafanaPrivateKey = readPrivateKey();
const grafanaPublicKey = createPublicKey(grafanaPrivateKey);
const grafanaPublicJwk = grafanaPublicKey.export({ format: 'jwk' });

export const config = {
  port: Number(process.env.PORT) || 3002,
  proxyPrefix: normalizePrefix(process.env.PROXY_PREFIX ?? '/grafana'),
  sessionCookieName: process.env.SESSION_COOKIE_NAME ?? 'jwt',
  appJwtSecret: process.env.APP_JWT_SECRET ?? process.env.JWT_SECRET ?? 'dev-secret',
  grafanaBaseUrl: process.env.GRAFANA_BASE_URL ?? 'http://localhost:3000',
  grafanaPathPrefix: normalizePrefix(process.env.GRAFANA_PATH_PREFIX ?? ''),
  grafanaTlsSkipVerify: process.env.GRAFANA_TLS_SKIP_VERIFY === 'true',
  grafanaJwtHeader: process.env.GRAFANA_JWT_HEADER ?? 'X-JWT-Assertion',
  grafanaJwtKeyId: process.env.GRAFANA_JWT_KEY_ID ?? 'grafana-proxy',
  grafanaJwtIssuer: process.env.GRAFANA_JWT_ISSUER ?? 'wearables-grafana-proxy',
  grafanaJwtAudience: process.env.GRAFANA_JWT_AUDIENCE ?? 'grafana',
  grafanaJwtTtlSeconds: Number(process.env.GRAFANA_JWT_TTL_SECONDS) || 300,
  grafanaDefaultRole: process.env.GRAFANA_DEFAULT_ROLE ?? 'Viewer',
  grafanaOrgId: process.env.GRAFANA_ORG_ID ?? '',
  grafanaJwtPrivateKey: grafanaPrivateKey,
  grafanaPublicJwk: {
    ...grafanaPublicJwk,
    kid: process.env.GRAFANA_JWT_KEY_ID ?? 'grafana-proxy',
    use: 'sig',
    alg: 'RS256',
  },
} as const;

export type { JwtPayload };
