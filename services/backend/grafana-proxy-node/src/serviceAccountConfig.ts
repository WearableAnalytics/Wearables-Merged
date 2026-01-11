import 'dotenv/config';

const normalizePrefix = (value: string): string => {
  const trimmed = value.trim();
  if (!trimmed || trimmed === '/') return '';
  const withSlash = trimmed.startsWith('/') ? trimmed : `/${trimmed}`;
  return withSlash.endsWith('/') ? withSlash.slice(0, -1) : withSlash;
};

export const serviceAccountConfig = {
  saProxyPrefix: normalizePrefix(process.env.SA_PROXY_PREFIX ?? '/grafana-sa'),
  grafanaBaseUrl: process.env.GRAFANA_BASE_URL ?? 'http://localhost:3000',
  grafanaPathPrefix: normalizePrefix(process.env.GRAFANA_PATH_PREFIX ?? ''),
  grafanaTlsSkipVerify: process.env.GRAFANA_TLS_SKIP_VERIFY === 'true',
  serviceAccountToken: process.env.GRAFANA_SERVICE_ACCOUNT_TOKEN ?? '',
} as const;
