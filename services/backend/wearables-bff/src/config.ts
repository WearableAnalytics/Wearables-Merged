/**
 * Configuration module for the wearables BFF service
 * Centralizes all environment variables and configuration
 */

import 'dotenv/config';

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

const requireOneOfEnv = <T extends string>(name: string, allowedValues: readonly T[]): T => {
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
  throw new Error(`Invalid configuration: ${name} must be exactly "true" or "false".`);
};

const requireBooleanEnv = (name: string): boolean => {
  return parseBooleanStrict(requireEnv(name).toLowerCase(), name);
};

const requireUrlEnv = (name: string): string => {
  const value = requireEnv(name);
  try {
    new URL(value);
  } catch {
    throw new Error(`Invalid configuration: ${name} must be a valid absolute URL.`);
  }
  return value;
};

const requirePositiveIntEnv = (name: string): number => {
  const value = requireEnv(name);
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`Invalid configuration: ${name} must be a positive integer.`);
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
  'TOKEN_ISSUER',
  'JWT_SECRET',
] as const;

const missing = requiredEnvVars.filter(name => optionalEnv(name) === undefined);
if (missing.length) throw new Error(`Missing required configuration: ${missing.join(', ')}`);

const nodeEnv = requireOneOfEnv<NodeEnv>('NODE_ENV', ['development', 'production']);
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
    throw new Error('Invalid configuration: EXTRACTION_API_URL must be a valid absolute URL.');
  }
}
const extractionApiUrl = extractionApiUrlRaw?.replace(/\/$/, '');

// Strict env-driven auth/token configuration.
const authSessionExpirySeconds = requirePositiveIntEnv('AUTH_SESSION_EXPIRY_SECONDS');
// Case tokens are what phones upload with, so they stay valid for 3 years by default.
const DEFAULT_CASE_TOKEN_EXPIRY_SECONDS = 3 * 365 * 24 * 60 * 60;
const caseTokenExpirySeconds =
  optionalEnv('CASE_TOKEN_EXPIRY_SECONDS') === undefined
    ? DEFAULT_CASE_TOKEN_EXPIRY_SECONDS
    : requirePositiveIntEnv('CASE_TOKEN_EXPIRY_SECONDS');
const tokenIssuer = requireEnv('TOKEN_ISSUER');

const jwtSecret = requireEnv('JWT_SECRET');
if (jwtSecret.length < 32) throw new Error('JWT_SECRET must contain at least 32 characters.');
const controlWriteToken = requireEnv('CONTROL_WRITE_TOKEN');
const apiTokenServiceToken = requireEnv('API_TOKEN_SERVICE_TOKEN');
if (controlWriteToken === apiTokenServiceToken) throw new Error('Workload credentials must be distinct.');
if (optionalEnv('ALLOW_DEV_AUTH_BYPASS') === 'true')
  throw new Error('Email-only development login has been removed. Use a named account password.');
if (isProduction && optionalEnv('COOKIE_SECURE') === 'false')
  throw new Error('Production requires secure cookies.');
if (isProduction && new URL(databaseApiUrl).protocol !== 'https:')
  throw new Error('Password authority requests require HTTPS in production.');

const parseCsv = (value: string): string[] =>
  value
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean);

const frontendOrigins = parseCsv(requireEnv('FRONTEND_ORIGINS'));
if (frontendOrigins.length === 0) {
  throw new Error('Invalid configuration: FRONTEND_ORIGINS must contain at least one origin.');
}
for (const origin of frontendOrigins) {
  try {
    new URL(origin);
  } catch {
    throw new Error(`Invalid configuration: FRONTEND_ORIGINS contains invalid URL: ${origin}`);
  }
}

const cookieSecureRaw = optionalEnv('COOKIE_SECURE');
const cookieSecure =
  cookieSecureRaw === undefined
    ? undefined
    : parseBooleanStrict(cookieSecureRaw.toLowerCase(), 'COOKIE_SECURE');

if (isProduction && [backendUrl, frontendRedirectUrl, ...frontendOrigins].some(value => new URL(value).protocol !== 'https:'))
  throw new Error('Production browser and email-link URLs must use HTTPS.');

export const config = {
  controlWriteToken,
  apiTokenServiceToken,
  controlMaxInflightRequests: 16,
  controlTimeoutSeconds: 5,
  httpMaxInflightRequests: 64,
  port,
  nodeEnv,
  isProduction,
  apiPrefix,
  logLevel,
  frontendOrigins,
  frontendRedirectUrl,
  backendUrl,
  cookieSecure,
  jwtSecret,
  authSessionExpirySeconds,
  caseTokenExpirySeconds,
  tokenIssuer,
  extractionApiUrl,
  databaseApi: {
    baseUrl: databaseApiUrl,
    timeout: databaseApiTimeout,
  },
  useMockData,
} as const;

export default config;
