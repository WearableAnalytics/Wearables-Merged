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

const optionalPositiveIntEnv = (name: string): number | undefined => {
  const value = optionalEnv(name);
  if (value === undefined) return undefined;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`Invalid configuration: ${name} must be a positive integer.`);
  }
  return parsed;
};

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
const researcherApiAccessToken = requireEnv('RESEARCHER_API_ACCESS_TOKEN');

// Optional tuning envs with safe defaults.
const authSessionExpirySeconds = optionalPositiveIntEnv('AUTH_SESSION_EXPIRY_SECONDS') ?? 604800;
const magicLinkExpirySeconds = optionalPositiveIntEnv('MAGIC_LINK_EXPIRY_SECONDS') ?? 900;
const caseTokenExpirySeconds = optionalPositiveIntEnv('CASE_TOKEN_EXPIRY_SECONDS') ?? 691200;
const tokenIssuer = optionalEnv('TOKEN_ISSUER') ?? 'wearables-bff';

const jwtSecretRaw = optionalEnv('JWT_SECRET');
if (!jwtSecretRaw && (isProduction || !useMockData)) {
  throw new Error(
    'Invalid configuration: JWT_SECRET is required when NODE_ENV=production or USE_MOCK_DATA=false.',
  );
}

if (isProduction && jwtSecretRaw === 'dev-secret') {
  throw new Error('Invalid configuration: JWT_SECRET cannot be "dev-secret" in production.');
}

const jwtSecret = jwtSecretRaw ?? 'dev-secret';

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

const adminEmails = parseCsv(optionalEnv('ADMIN_EMAILS') ?? '');
const mailerFromName = optionalEnv('MAILER_FROM_NAME');
const mailerFromEmail = optionalEnv('MAILER_FROM_EMAIL');
const brevoApiKey = optionalEnv('BREVO_API_KEY');

if (isProduction && !mailerFromName) {
  throw new Error(
    'Invalid configuration: MAILER_FROM_NAME is required when NODE_ENV=production.',
  );
}

if (isProduction && !mailerFromEmail) {
  throw new Error(
    'Invalid configuration: MAILER_FROM_EMAIL is required when NODE_ENV=production.',
  );
}

if (isProduction && mailerFromEmail && !mailerFromEmail.includes('@')) {
  throw new Error(
    'Invalid configuration: MAILER_FROM_EMAIL must be a valid email when NODE_ENV=production.',
  );
}

if (isProduction && !brevoApiKey) {
  throw new Error('Invalid configuration: BREVO_API_KEY is required when NODE_ENV=production.');
}

export const config = {
  port,
  nodeEnv,
  isProduction,
  apiPrefix,
  logLevel,
  mailerFromName,
  mailerFromEmail,
  brevoApiKey,
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
  researcherApiAccessToken,
  databaseApi: {
    baseUrl: databaseApiUrl,
    timeout: databaseApiTimeout,
  },
  useMockData,
} as const;

export default config;
