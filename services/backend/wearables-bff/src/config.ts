/**
 * Configuration module for the wearables BFF service
 * Centralizes all environment variables and configuration
 */

import 'dotenv/config';
import { isIP } from 'node:net';

type NodeEnv = 'development' | 'production';
type LogLevel = 'trace' | 'debug' | 'info' | 'warn' | 'error';

const optionalEnv = (name: string): string | undefined => {
  const value = (process.env[name] ?? '').trim();
  return value || undefined;
};

const requireEnv = (name: string): string => {
  const value = optionalEnv(name);
  if (!value) {
    throw new Error(`Invalid configuration: ${name} is required.`);
  }
  return value;
};

const requireOneOfEnv = <T extends string>(
  name: string,
  allowedValues: readonly T[],
): T => {
  const value = requireEnv(name);
  if (!allowedValues.includes(value as T)) {
    throw new Error(
      `Invalid configuration: ${name} must be one of: ${allowedValues.join(', ')}.`,
    );
  }
  return value as T;
};

const parseBooleanStrict = (value: string, name: string): boolean => {
  if (value === 'true') return true;
  if (value === 'false') return false;
  throw new Error(
    `Invalid configuration: ${name} must be exactly "true" or "false".`,
  );
};

const requireBooleanEnv = (name: string): boolean => {
  return parseBooleanStrict(requireEnv(name).toLowerCase(), name);
};

const requireUrlEnv = (name: string): string => {
  const value = requireEnv(name);
  try {
    new URL(value);
  } catch {
    throw new Error(
      `Invalid configuration: ${name} must be a valid absolute URL.`,
    );
  }
  return value;
};

const requirePositiveIntEnv = (name: string): number => {
  const value = requireEnv(name);
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(
      `Invalid configuration: ${name} must be a positive integer.`,
    );
  }
  return parsed;
};

const requiredEnvVars = [
  'PORT',
  'NODE_ENV',
  'API_PREFIX',
  'USE_MOCK_DATA',
  'LOG_LEVEL',
  'BACKEND_URL',
  'FRONTEND_REDIRECT_URL',
  'FRONTEND_ORIGINS',
  'DATABASE_API_URL',
  'DATABASE_API_TIMEOUT',
  'AUTH_SESSION_EXPIRY_SECONDS',
  'MAGIC_LINK_EXPIRY_SECONDS',
  'TOKEN_ISSUER',
  'JWT_SECRET',
] as const;

const missingRequiredEnvVars = requiredEnvVars.filter(
  (name) => optionalEnv(name) === undefined,
);
if (missingRequiredEnvVars.length > 0) {
  throw new Error(
    `Invalid configuration: missing required environment variables: ${missingRequiredEnvVars.join(
      ', ',
    )}.`,
  );
}

const nodeEnv = requireOneOfEnv<NodeEnv>('NODE_ENV', [
  'development',
  'production',
]);
const isProduction = nodeEnv === 'production';
const useMockData = requireBooleanEnv('USE_MOCK_DATA');
const logLevel = requireOneOfEnv<LogLevel>('LOG_LEVEL', [
  'trace',
  'debug',
  'info',
  'warn',
  'error',
]);
const port = requirePositiveIntEnv('PORT');
const apiPrefixRaw = requireEnv('API_PREFIX');
if (!apiPrefixRaw.startsWith('/')) {
  throw new Error('Invalid configuration: API_PREFIX must start with "/".');
}
const apiPrefix = apiPrefixRaw.replace(/\/$/, '');
if (!apiPrefix) {
  throw new Error('Invalid configuration: API_PREFIX cannot be empty.');
}

const backendUrl = requireUrlEnv('BACKEND_URL');
const frontendRedirectUrl = requireUrlEnv('FRONTEND_REDIRECT_URL');
const databaseApiUrl = requireUrlEnv('DATABASE_API_URL');
const databaseApiTimeout = requirePositiveIntEnv('DATABASE_API_TIMEOUT');
// Optional: base URL of the extraction service. When set, it is served under
// `${API_PREFIX}/extraction` for researchers and admins (see api/routes/extraction.ts).
const extractionApiUrlRaw = optionalEnv('EXTRACTION_API_URL');
if (extractionApiUrlRaw) {
  try {
    new URL(extractionApiUrlRaw);
  } catch {
    throw new Error(
      'Invalid configuration: EXTRACTION_API_URL must be a valid absolute URL.',
    );
  }
}
const extractionApiUrl = extractionApiUrlRaw?.replace(/\/$/, '');

// Strict env-driven auth/token configuration.
const authSessionExpirySeconds = requirePositiveIntEnv(
  'AUTH_SESSION_EXPIRY_SECONDS',
);
const requestedMagicLinkExpirySeconds = requirePositiveIntEnv(
  'MAGIC_LINK_EXPIRY_SECONDS',
);
if (requestedMagicLinkExpirySeconds > 3600)
  throw new Error('MAGIC_LINK_EXPIRY_SECONDS must not exceed 3600.');
// Case tokens are what phones upload with, so they stay valid for 3 years by default.
const DEFAULT_CASE_TOKEN_EXPIRY_SECONDS = 3 * 365 * 24 * 60 * 60;
const caseTokenExpirySeconds =
  optionalEnv('CASE_TOKEN_EXPIRY_SECONDS') === undefined
    ? DEFAULT_CASE_TOKEN_EXPIRY_SECONDS
    : requirePositiveIntEnv('CASE_TOKEN_EXPIRY_SECONDS');
const tokenIssuer = requireEnv('TOKEN_ISSUER');

const jwtSecret = requireEnv('JWT_SECRET');
if (jwtSecret.length < 32)
  throw new Error('JWT_SECRET must contain at least 32 characters.');
const controlWriteToken = requireEnv('CONTROL_WRITE_TOKEN');
const apiTokenServiceToken = requireEnv('API_TOKEN_SERVICE_TOKEN');
if (controlWriteToken === apiTokenServiceToken)
  throw new Error('Workload credentials must be distinct.');
const devAuthBypass = optionalEnv('ALLOW_DEV_AUTH_BYPASS') === 'true';
const listenHost = optionalEnv('LISTEN_HOST') ?? (isProduction ? '0.0.0.0' : '127.0.0.1');
if (!isIP(listenHost)) throw new Error('LISTEN_HOST must be an IP address.');
if (isProduction && (devAuthBypass || cookieSecureIsFalse()))
  throw new Error('Production requires verified login and secure cookies.');
if (devAuthBypass && !['127.0.0.1', '::1'].includes(listenHost))
  throw new Error('ALLOW_DEV_AUTH_BYPASS requires a loopback listen address.');
function cookieSecureIsFalse() {
  return optionalEnv('COOKIE_SECURE') === 'false';
}

const parseCsv = (value: string): string[] =>
  value
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean);

const frontendOrigins = parseCsv(requireEnv('FRONTEND_ORIGINS'));
if (frontendOrigins.length === 0) {
  throw new Error(
    'Invalid configuration: FRONTEND_ORIGINS must contain at least one origin.',
  );
}
for (const origin of frontendOrigins) {
  try {
    new URL(origin);
  } catch {
    throw new Error(
      `Invalid configuration: FRONTEND_ORIGINS contains invalid URL: ${origin}`,
    );
  }
}

const cookieSecureRaw = optionalEnv('COOKIE_SECURE');
const cookieSecure =
  cookieSecureRaw === undefined
    ? undefined
    : parseBooleanStrict(cookieSecureRaw.toLowerCase(), 'COOKIE_SECURE');

const adminEmails = parseCsv(optionalEnv('ADMIN_EMAILS') ?? '');
const mailerFromName = optionalEnv('MAILER_FROM_NAME');
const mailerFromEmail = optionalEnv('MAILER_FROM_EMAIL');
const brevoApiKeyRaw = optionalEnv('BREVO_API_KEY');
const brevoApiKey =
  brevoApiKeyRaw && brevoApiKeyRaw !== 'disabled' ? brevoApiKeyRaw : undefined;
const emailDeliveryEnabled = isProduction && Boolean(brevoApiKey);
const operatorMagicLinkLogging = isProduction && !emailDeliveryEnabled &&
  parseBooleanStrict(optionalEnv('ALLOW_OPERATOR_MAGIC_LINK_LOGGING') ?? 'false', 'ALLOW_OPERATOR_MAGIC_LINK_LOGGING');
// Log readers can use an unused link. Bound this temporary delivery mode to five minutes.
const magicLinkExpirySeconds = operatorMagicLinkLogging
  ? Math.min(requestedMagicLinkExpirySeconds, 300) : requestedMagicLinkExpirySeconds;

if (emailDeliveryEnabled && !mailerFromName) {
  throw new Error(
    'Invalid configuration: MAILER_FROM_NAME is required when NODE_ENV=production.',
  );
}

if (emailDeliveryEnabled && !mailerFromEmail) {
  throw new Error(
    'Invalid configuration: MAILER_FROM_EMAIL is required when NODE_ENV=production.',
  );
}

if (emailDeliveryEnabled && mailerFromEmail && !mailerFromEmail.includes('@')) {
  throw new Error(
    'Invalid configuration: MAILER_FROM_EMAIL must be a valid email when NODE_ENV=production.',
  );
}

if (operatorMagicLinkLogging)
  console.warn('Temporary operator login-link logging is enabled. Restrict access to these credential logs.');
else if (isProduction && !emailDeliveryEnabled)
  console.warn('Email sign-in is unavailable: email delivery is disabled.');

if (
  isProduction &&
  [backendUrl, frontendRedirectUrl, ...frontendOrigins].some(
    (value) => new URL(value).protocol !== 'https:',
  )
)
  throw new Error('Production browser and email-link URLs must use HTTPS.');

const databaseOperatorToken = requireEnv('DATABASE_OPERATOR_TOKEN');
if (
  databaseOperatorToken.length < 32 ||
  databaseOperatorToken === controlWriteToken ||
  databaseOperatorToken === apiTokenServiceToken
)
  throw new Error(
    'Set a distinct DATABASE_OPERATOR_TOKEN of at least 32 characters.',
  );
const allowPrivateAuthorityHttp = parseBooleanStrict(
  optionalEnv('ALLOW_PRIVATE_AUTHORITY_HTTP') ?? 'false', 'ALLOW_PRIVATE_AUTHORITY_HTTP');
const authorityUrl = new URL(databaseApiUrl);
const isClusterService = /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.svc(?:\.cluster\.local)?$/.test(authorityUrl.hostname);
if (authorityUrl.username || authorityUrl.password ||
    (isProduction && authorityUrl.protocol !== 'https:' &&
      !(allowPrivateAuthorityHttp && authorityUrl.protocol === 'http:' && isClusterService)))
  throw new Error('Production account authority must use HTTPS or explicitly enabled Kubernetes service HTTP.');
const trustedProxyCidrs = parseCsv(optionalEnv('TRUSTED_PROXY_CIDRS') ?? '');
if (
  trustedProxyCidrs.some(
    (value) => !/^[0-9a-fA-F.:]+(?:\/\d{1,3})?$/.test(value),
  )
)
  throw new Error(
    'TRUSTED_PROXY_CIDRS must contain only explicit IP addresses/CIDRs.',
  );

if (requestedMagicLinkExpirySeconds > 3600)
  throw new Error('Email links must expire within 3600 seconds.');
if (
  devAuthBypass &&
  [backendUrl, frontendRedirectUrl, databaseApiUrl, ...frontendOrigins].some(
    (value) =>
      !['127.0.0.1', 'localhost', '[::1]'].includes(new URL(value).hostname),
  )
)
  throw new Error(
    'ALLOW_DEV_AUTH_BYPASS requires loopback-only development URLs.',
  );
export const config = {
  listenHost,
  databaseOperatorToken,
  trustedProxyCidrs,
  controlWriteToken,
  apiTokenServiceToken,
  devAuthBypass,
  controlMaxInflightRequests: 16,
  controlTimeoutSeconds: 5,
  httpMaxInflightRequests: 64,
  port,
  nodeEnv,
  isProduction,
  apiPrefix,
  logLevel,
  mailerFromName,
  mailerFromEmail,
  brevoApiKey,
  emailDeliveryEnabled,
  operatorMagicLinkLogging,
  allowPrivateAuthorityHttp,
  frontendOrigins,
  frontendRedirectUrl,
  backendUrl,
  cookieSecure,
  jwtSecret,
  authSessionExpirySeconds,
  magicLinkExpirySeconds,
  caseTokenExpirySeconds,
  tokenIssuer,
  adminEmails,
  extractionApiUrl,
  databaseApi: {
    baseUrl: databaseApiUrl,
    timeout: databaseApiTimeout,
  },
  useMockData,
} as const;

export default config;
