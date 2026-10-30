import type { NextFunction, Request, Response } from 'express';
import jwt from 'jsonwebtoken';
import config from './config.js';
import { sendControlError } from './clients/controlApi.js';
import { logger } from './logger.js';
import { getUserById } from './services/userStore.js';
import type { AccessRequestStatus, NonAdminRole, UserStatus } from './services/userStore.js';

export interface JwtPayload {
  userId: string;
  sessionVersion: number;
  email: string;
  name?: string;
  isAdmin?: boolean;
  roles?: NonAdminRole[];
  status?: UserStatus;
  adminRequestStatus?: AccessRequestStatus;
  roleRequestStatuses?: Record<NonAdminRole, AccessRequestStatus>;
}

declare global {
  namespace Express {
    interface Request {
      user?: JwtPayload;
    }
  }
}

type CookieRequest = Request & { cookies?: Record<string, string> };

let activeHttpRequests = 0;
export const admitHttpRequest = (req: Request, res: Response, next: NextFunction): void => {
  if (
    req.method === 'OPTIONS' ||
    (['GET', 'HEAD'].includes(req.method) && req.path === `${config.apiPrefix}/health`)
  ) {
    next();
    return;
  }
  if (activeHttpRequests >= config.httpMaxInflightRequests) {
    res.setHeader('Retry-After', '1');
    res.status(503).json({ error: 'Request capacity exceeded', code: 'HTTP_CAPACITY' });
    return;
  }
  activeHttpRequests++;
  let released = false;
  const release = () => {
    if (!released) {
      released = true;
      activeHttpRequests--;
    }
  };
  res.once('finish', release);
  res.once('close', release);
  next();
};

const canonicalOrigin = (value: string): string | undefined => {
  if (value.length > 2048) return undefined;
  try {
    const url = new URL(value);
    if (
      !['http:', 'https:'].includes(url.protocol) ||
      url.username ||
      url.password ||
      value !== url.origin
    )
      return undefined;
    return url.origin;
  } catch {
    return undefined;
  }
};
const commandOrigins = new Set(
  [
    ...config.frontendOrigins.map((value) => canonicalOrigin(value)),
    new URL(config.backendUrl).origin,
  ].filter((value): value is string => Boolean(value)),
);

/** CORS does not stop browsers from sending cookie-authenticated commands. */
export const requireCommandOrigin = (req: Request, res: Response, next: NextFunction): void => {
  if (['GET', 'HEAD', 'OPTIONS'].includes(req.method)) {
    next();
    return;
  }
  const raw = req.headers.origin;
  const origin = typeof raw === 'string' ? canonicalOrigin(raw) : undefined;
  if (!origin || !commandOrigins.has(origin)) {
    res
      .status(403)
      .json({ error: 'An approved request Origin is required', code: 'ORIGIN_REQUIRED' });
    return;
  }
  next();
};

export const parseCookies = (cookieHeader?: string): Record<string, string> => {
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

export const getUserFromRequest = async (req: Request, signal?: AbortSignal): Promise<JwtPayload | undefined> => {
  let decoded: jwt.JwtPayload;
  try {
    const cookies = (req as CookieRequest).cookies ?? parseCookies(req.headers.cookie);
    if (!cookies.jwt) return undefined;
    const verified = jwt.verify(cookies.jwt, config.jwtSecret, {
      algorithms: ['HS256'],
      issuer: config.tokenIssuer,
      audience: 'wearables-web',
    });
    if (typeof verified === 'string') return undefined;
    decoded = verified;
    if (
      decoded.type !== 'web-session' ||
      typeof decoded.userId !== 'string' ||
      !decoded.userId ||
      typeof decoded.email !== 'string' ||
      decoded.sub !== decoded.userId ||
      !Number.isInteger(decoded.sessionVersion) ||
      decoded.sessionVersion < 1 ||
      typeof decoded.exp !== 'number' ||
      !Number.isFinite(decoded.exp)
    )
      return undefined;
  } catch {
    return undefined;
  }
  // Do not treat a control outage as a missing user or accept cached authority.
  const user = await getUserById(decoded.userId, signal);
  if (!user || user.email !== decoded.email || user.authVersion !== decoded.sessionVersion)
    return undefined;
  return {
    userId: user.id,
    email: user.email,
    name: user.name,
    isAdmin: user.isAdmin,
    roles: user.roles,
    status: user.status,
    sessionVersion: user.authVersion,
    adminRequestStatus: user.adminRequestStatus,
    roleRequestStatuses: user.roleRequestStatuses,
  };
};

// Basic Authentication
const authenticate = async (req: Request, res: Response, next: NextFunction): Promise<void> => {
  try {
    const user = await getUserFromRequest(req);

    if (!user) {
      res.status(401).json({ error: 'Authentication required' });
      return;
    }

    if (user.status === 'pending') {
      res.status(403).json({
        error: 'Account pending approval',
        message: 'Your account is awaiting admin approval.',
        code: 'PENDING_APPROVAL',
      });
      return;
    }

    if (user.status === 'denied') {
      res.status(403).json({
        error: 'Account denied',
        message: 'Your access request was denied. Please contact an administrator.',
        code: 'ACCOUNT_DENIED',
      });
      return;
    }

    req.user = user;
    next();
  } catch (err) {
    if (sendControlError(res, err)) return;
    res.status(401).json({ error: 'Invalid or expired token' });
  }
};

const requireAdmin = (req: Request, res: Response, next: NextFunction): void => {
  if (!req.user) {
    res.status(401).json({ error: 'Authentication required' });
    return;
  }

  if (!req.user.isAdmin) {
    res.status(403).json({
      error: 'Admin access required',
      message: 'You do not have permission to access this resource.',
      code: 'ADMIN_REQUIRED',
    });
    return;
  }

  next();
};

const requirePractitionerOrAdmin = (req: Request, res: Response, next: NextFunction): void => {
  if (!req.user) {
    res.status(401).json({ error: 'Authentication required' });
    return;
  }

  if (req.user.isAdmin || req.user.roles?.includes('practitioner')) {
    next();
    return;
  }

  res.status(403).json({
    error: 'Practitioner access required',
    message: 'You do not have permission to access this resource.',
    code: 'PRACTITIONER_REQUIRED',
  });
};

const requireResearcherOrAdmin = (req: Request, res: Response, next: NextFunction): void => {
  if (!req.user) {
    res.status(401).json({ error: 'Authentication required' });
    return;
  }

  if (req.user.isAdmin || req.user.roles?.includes('researcher')) {
    next();
    return;
  }

  res.status(403).json({
    error: 'Researcher access required',
    message: 'You do not have permission to access this resource.',
    code: 'RESEARCHER_REQUIRED',
  });
};

export const auth = {
  required: authenticate,
  practitionerOrAdmin: requirePractitionerOrAdmin,
  researcherOrAdmin: requireResearcherOrAdmin,
  adminOnly: [authenticate, requireAdmin],
};

export function requestLogger(req: Request, res: Response, next: NextFunction) {
  const start = process.hrtime.bigint();

  res.on('finish', () => {
    const durationMs = Number(process.hrtime.bigint() - start) / 1_000_000;
    const level: 'error' | 'warn' | 'info' =
      res.statusCode >= 500 ? 'error' : res.statusCode >= 400 ? 'warn' : 'info';

    logger[level]('http.request', {
      method: req.method,
      route: typeof req.route?.path === 'string' ? req.route.path : 'unmatched',
      status: res.statusCode,
      durationMs: Number(durationMs.toFixed(2)),
    });
  });

  next();
}

// Error Handler
export function notFound(req: Request, res: Response, next: NextFunction) {
  res.status(404);
  const error = new Error(`Not found: ${req.path}`);
  next(error);
}

export function errorHandler(err: Error, _: Request, res: Response, __: NextFunction) {
  if (res.destroyed) return;
  if (res.headersSent) {
    res.end();
    return;
  }
  const proposed = (err as Error & { status?: number }).status;
  const status = proposed && proposed >= 400 && proposed < 500 ? proposed : 500;
  // Parser errors can retain raw JSON and cookies. Do not log or return them.
  if (status >= 500) logger.error('http.request.failed', { status });
  res.status(status).json({ error: status >= 500 ? 'Request failed' : 'Invalid request' });
}
