import type { NextFunction, Request, Response } from 'express';
import jwt from 'jsonwebtoken';
import config from './config.js';

export interface JwtPayload {
  userId: string;
  email: string;
  name?: string;
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
    return decoded;
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

    req.user = user;
    next();
  } catch (err) {
    res.status(401).json({ error: 'Invalid or expired token' });
  }
};

export const auth = {
  required: authenticate,
};

// Error Handler
export function notFound(req: Request, res: Response, next: NextFunction) {
  res.status(404);
  const error = new Error(`🔍 - Not Found - ${req.originalUrl}`);
  next(error);
}

export function errorHandler(err: Error, _: Request, res: Response, __: NextFunction) {
  const statusCode = res.statusCode !== 200 ? res.statusCode : 500;
  res.status(statusCode);
  res.json({
    message: err.message,
    stack: process.env.NODE_ENV !== 'development' ? '<redacted>' : err.stack,
  });
}
