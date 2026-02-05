import type { NextFunction, Request, Response } from 'express';
import jwt from 'jsonwebtoken';
import config from './config.js';
import { logger } from './logger.js';
import { getUserByEmail } from './services/userStore.js';
import type { AdminRequestStatus, UserRole, UserStatus } from './services/userStore.js';

export interface JwtPayload {
  userId: string;
  email: string;
  name?: string;
  role?: UserRole;
  status?: UserStatus;
  adminRequestStatus?: AdminRequestStatus;
}

declare global {
  namespace Express {
    interface Request {
      user?: JwtPayload;
    }
  }
}

type CookieRequest = Request & { cookies?: Record<string, string> };

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

export const getUserFromRequest = (req: Request): JwtPayload | undefined => {
  try {
    const cookies =
      (req as CookieRequest).cookies ??
      parseCookies(req.headers.cookie);
    const token = cookies.jwt;
    if (!token) return undefined;
    const decoded = jwt.verify(token, config.jwtSecret) as JwtPayload;
    if (!decoded.userId || !decoded.email) {
      throw new Error('Invalid token payload');
    }
    const userRecord = getUserByEmail(decoded.email);
    if (!userRecord || userRecord.id !== decoded.userId) {
      return undefined;
    }
    return {
      userId: userRecord.id,
      email: userRecord.email,
      name: userRecord.name,
      role: userRecord.role,
      status: userRecord.status,
      adminRequestStatus: userRecord.adminRequestStatus,
    };
  } catch (err) {
    return undefined;
  }
};

// Basic Authentication
const authenticate = (req: Request, res: Response, next: NextFunction): void => {
  try {
    const user = getUserFromRequest(req);

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
    res.status(401).json({ error: 'Invalid or expired token' });
  }
};

const requireAdmin = (req: Request, res: Response, next: NextFunction): void => {
  if (!req.user) {
    res.status(401).json({ error: 'Authentication required' });
    return;
  }

  if (req.user.role !== 'admin') {
    res.status(403).json({
      error: 'Admin access required',
      message: 'You do not have permission to access this resource.',
      code: 'ADMIN_REQUIRED',
    });
    return;
  }

  next();
};

export const auth = {
  required: authenticate,
  adminOnly: [authenticate, requireAdmin],
};

export function requestLogger(req: Request, res: Response, next: NextFunction) {
  const start = process.hrtime.bigint();

  res.on('finish', () => {
    const durationMs = Number(process.hrtime.bigint() - start) / 1_000_000;
    const level: 'error' | 'warn' | 'info' =
      res.statusCode >= 500 ? 'error' :
      res.statusCode >= 400 ? 'warn' :
      'info';

    logger[level]('HTTP request', {
      method: req.method,
      path: req.originalUrl,
      status: res.statusCode,
      durationMs: Number(durationMs.toFixed(2)),
      ip: req.ip,
    });
  });

  next();
}

// Error Handler
export function notFound(req: Request, res: Response, next: NextFunction) {
  res.status(404);
  const error = new Error(`🔍 - Not Found - ${req.originalUrl}`);
  next(error);
}

export function errorHandler(err: Error, _: Request, res: Response, __: NextFunction) {
  const statusCode = res.statusCode !== 200 ? res.statusCode : 500;
  res.status(statusCode);
  logger.error('Unhandled error', err);
  res.json({
    message: err.message,
    stack: process.env.NODE_ENV !== 'development' ? '<redacted>' : err.stack,
  });
}
