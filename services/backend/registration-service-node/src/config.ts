/**
 * Configuration module for the registration service
 * Centralizes all environment variables and configuration
 */

import 'dotenv/config';

const jwtSecret = process.env.JWT_SECRET || 'dev-secret';

export const config = {
  port: Number(process.env.PORT) || 3001,
  nodeEnv: process.env.NODE_ENV || 'development',
  apiPrefix: (process.env.API_PREFIX ?? '/api').replace(/\/$/, ''),
  
  frontendOrigins: (process.env.FRONTEND_URL ?? 'http://localhost:5173,http://localhost:8080')
    .split(',')
    .map((url) => url.trim())
    .filter(Boolean),
  
  jwtSecret,
  
  databaseApi: {
    baseUrl: process.env.DATABASE_API_URL || 'http://localhost:8000',
    timeout: Number(process.env.DATABASE_API_TIMEOUT) || 30000,
  },
  
  useMockData: process.env.USE_MOCK_DATA === 'true',
} as const;

export default config;
