import crypto from 'crypto';
import express from 'express';
import type { NextFunction, Request, Response } from 'express';
import { Readable } from 'stream';
import type { ReadableStream as WebReadableStream } from 'stream/web';
import config from '../../config.js';
import { logger } from '../../logger.js';
import { getUserFromRequest } from '../../middleware.js';

/**
 * Researcher-facing extraction API (services/backend/extraction-service), proxied
 * under `${API_PREFIX}/extraction`. Includes its Swagger UI at `/extraction/docs`.
 *
 * Access: a logged-in, approved researcher or admin (session cookie), or the
 * researcher API token from the web app's API Access page as a Bearer token.
 */
const router = express.Router();

const FORWARDED_RESPONSE_HEADERS = ['content-type', 'content-disposition', 'cache-control'];

const tokensMatch = (given: string, expected: string): boolean => {
  const a = crypto.createHash('sha256').update(given).digest();
  const b = crypto.createHash('sha256').update(expected).digest();
  return crypto.timingSafeEqual(a, b);
};

const bearerToken = (req: Request): string | undefined => {
  const header = req.headers.authorization;
  if (!header?.startsWith('Bearer ')) return undefined;
  return header.slice('Bearer '.length).trim() || undefined;
};

export const requireExtractionAccess = (req: Request, res: Response, next: NextFunction): void => {
  const token = bearerToken(req);
  if (token !== undefined) {
    if (tokensMatch(token, config.researcherApiAccessToken)) {
      next();
      return;
    }
    res.status(401).json({ error: 'Invalid API access token' });
    return;
  }

  const user = getUserFromRequest(req);
  if (!user) {
    res.status(401).json({ error: 'Authentication required' });
    return;
  }
  if (user.status === 'pending' || user.status === 'denied') {
    res.status(403).json({ error: 'Account not approved', code: 'ACCOUNT_NOT_APPROVED' });
    return;
  }
  if (!user.isAdmin && !user.roles?.includes('researcher')) {
    res.status(403).json({ error: 'Researcher access required', code: 'RESEARCHER_REQUIRED' });
    return;
  }
  req.user = user;
  next();
};

router.get('/*', requireExtractionAccess, async (req: Request, res: Response) => {
  if (!config.extractionApiUrl) {
    res.status(503).json({ error: 'Extraction API is not configured' });
    return;
  }

  // req.url is relative to the mount point, e.g. /v1/measurements?patient_id=...
  const target = `${config.extractionApiUrl}${req.url}`;
  const abort = new AbortController();
  res.on('close', () => abort.abort());

  try {
    const upstream = await fetch(target, {
      headers: { accept: req.headers.accept ?? '*/*' },
      signal: abort.signal,
    });

    res.status(upstream.status);
    for (const name of FORWARDED_RESPONSE_HEADERS) {
      const value = upstream.headers.get(name);
      if (value) res.setHeader(name, value);
    }
    if (!upstream.body) {
      res.end();
      return;
    }
    Readable.fromWeb(upstream.body as WebReadableStream).pipe(res);
  } catch (error) {
    if (abort.signal.aborted) return;
    logger.error('Extraction API request failed', error as Error);
    if (!res.headersSent) {
      res.status(502).json({ error: 'Extraction API unavailable' });
    } else {
      res.end();
    }
  }
});

export default router;
