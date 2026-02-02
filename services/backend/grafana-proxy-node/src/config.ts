import 'dotenv/config';
import { readFileSync } from 'fs';

const normalizePrefix = (value: string): string => {
  const trimmed = value.trim();
  if (!trimmed || trimmed === '/') return '';
  const withSlash = trimmed.startsWith('/') ? trimmed : `/${trimmed}`;
  return withSlash.endsWith('/') ? withSlash.slice(0, -1) : withSlash;
};

const readPrivateKey = (): string | null => {
  if (process.env.GRAFANA_JWT_PRIVATE_KEY) {
    return process.env.GRAFANA_JWT_PRIVATE_KEY.replace(/\\n/g, '\n');
  }
  if (process.env.GRAFANA_JWT_PRIVATE_KEY_PATH) {
    return readFileSync(process.env.GRAFANA_JWT_PRIVATE_KEY_PATH, 'utf8');
  }
  return null;
};

const grafanaPrivateKey = readPrivateKey();

export const config = {
  port: Number(process.env.PORT) || 3002,
  proxyPrefix: normalizePrefix(process.env.PROXY_PREFIX ?? '/grafana'),
  grafanaBaseUrl: process.env.GRAFANA_BASE_URL ?? 'http://localhost:3000',
  grafanaPathPrefix: normalizePrefix(process.env.GRAFANA_PATH_PREFIX ?? ''),
  grafanaTlsSkipVerify: process.env.GRAFANA_TLS_SKIP_VERIFY === 'true',
  grafanaJwtHeader: process.env.GRAFANA_JWT_HEADER ?? 'X-JWT-Assertion',
  grafanaJwtIssuer: process.env.GRAFANA_JWT_ISSUER ?? 'wearables-grafana-proxy',
  grafanaJwtAudience: process.env.GRAFANA_JWT_AUDIENCE ?? 'grafana',
  grafanaJwtTtlSeconds: Number(process.env.GRAFANA_JWT_TTL_SECONDS) || 300,
  grafanaJwtSubject: process.env.GRAFANA_JWT_SUBJECT ?? '',
  grafanaJwtEmail: process.env.GRAFANA_JWT_EMAIL ?? '',
  grafanaJwtName: process.env.GRAFANA_JWT_NAME ?? '',
  grafanaJwtRole: process.env.GRAFANA_JWT_ROLE ?? '',
  grafanaOrgId: process.env.GRAFANA_ORG_ID ?? '',
  grafanaJwtPrivateKey: grafanaPrivateKey,
  grafanaJwtIatSkewSeconds: Number(process.env.GRAFANA_JWT_IAT_SKEW_SECONDS) || 0,
};
