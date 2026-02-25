import config from './config.js';

export type LogLevel = 'trace' | 'debug' | 'info' | 'warn' | 'error';

const levelWeights: Record<LogLevel, number> = {
  trace: 10,
  debug: 20,
  info: 30,
  warn: 40,
  error: 50,
};

const serviceName = 'wearables-bff';

const currentLevel = config.logLevel as LogLevel;

const isLevelEnabled = (level: LogLevel) => levelWeights[level] >= levelWeights[currentLevel];

type LogMeta =
  | Record<string, unknown>
  | Error
  | string
  | number
  | boolean
  | null
  | undefined;

const normalizeMeta = (meta?: LogMeta) => {
  if (!meta) return undefined;
  if (meta instanceof Error) {
    return {
      error: {
        name: meta.name,
        message: meta.message,
        stack: meta.stack,
      },
    };
  }
  if (typeof meta === 'object') {
    return meta as Record<string, unknown>;
  }
  return { meta };
};

const writeLog = (level: LogLevel, message: string, meta?: LogMeta) => {
  if (!isLevelEnabled(level)) return;

  const payload = {
    timestamp: new Date().toISOString(),
    level,
    service: serviceName,
    message,
    ...(normalizeMeta(meta) ?? {}),
  };

  const line = JSON.stringify(payload);
  if (level === 'error') {
    console.error(line);
  } else if (level === 'warn') {
    console.warn(line);
  } else {
    console.log(line);
  }
};

export const logger = {
  trace: (message: string, meta?: LogMeta) => writeLog('trace', message, meta),
  debug: (message: string, meta?: LogMeta) => writeLog('debug', message, meta),
  info: (message: string, meta?: LogMeta) => writeLog('info', message, meta),
  warn: (message: string, meta?: LogMeta) => writeLog('warn', message, meta),
  error: (message: string, meta?: LogMeta) => writeLog('error', message, meta),
  isLevelEnabled,
  level: currentLevel,
};
