/**
 * Configuration module for the registration service
 * Centralizes all environment variables and configuration
 */

import 'dotenv/config';

const jwtSecret = process.env.JWT_SECRET || 'dev-secret';
const nodeEnv = process.env.NODE_ENV || 'development';
const isProduction = nodeEnv === 'production';
const defaultLogLevel = nodeEnv === 'production' ? 'info' : 'debug';
const logLevelRaw = (process.env.LOG_LEVEL || defaultLogLevel).toLowerCase();
const allowedLogLevels = new Set(['trace', 'debug', 'info', 'warn', 'error']);
const logLevel = allowedLogLevels.has(logLevelRaw) ? logLevelRaw : defaultLogLevel;
const mailerEnabledRaw = (process.env.MAILER_ENABLED ?? 'true').trim().toLowerCase();
const mailerEnabled = mailerEnabledRaw !== 'false';

if (isProduction && !mailerEnabled) {
  throw new Error(
    'Invalid configuration: MAILER_ENABLED=false is not allowed when NODE_ENV=production.',
  );
}

const adminEmails = (process.env.ADMIN_EMAILS ?? '')
  .split(',')
  .map((email) => email.trim())
  .filter(Boolean);
const researcherApiAccessToken =
  (process.env.RESEARCHER_API_ACCESS_TOKEN ?? 'dummy-researcher-api-token').trim() ||
  'dummy-researcher-api-token';

export const config = {
  port: Number(process.env.PORT) || 3001,
  nodeEnv,
  isProduction,
  apiPrefix: (process.env.API_PREFIX ?? '/api').replace(/\/$/, ''),
  logLevel,
  mailerEnabled,
  
  frontendOrigins: (process.env.FRONTEND_URL ?? 'http://localhost:5173,http://localhost:8080')
    .split(',')
    .map((url) => url.trim())
    .filter(Boolean),
  
  jwtSecret,
  adminEmails,
  researcherApiAccessToken,
  
  databaseApi: {
    baseUrl: process.env.DATABASE_API_URL || 'http://localhost:8000',
    timeout: Number(process.env.DATABASE_API_TIMEOUT) || 30000,
  },
  
  useMockData: process.env.USE_MOCK_DATA === 'true',
} as const;

export default config;
