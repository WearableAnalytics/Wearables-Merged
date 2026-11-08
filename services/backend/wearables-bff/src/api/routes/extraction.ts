import express from 'express';
import jwt from 'jsonwebtoken';
import type { NextFunction, Request, Response } from 'express';
import { Readable } from 'stream';
import type { ReadableStream as WebReadableStream } from 'stream/web';
import config from '../../config.js';
import { logger } from '../../logger.js';
import { getUserFromRequest } from '../../middleware.js';
import { checkApiToken } from '../../services/apiTokens.js';

/**
 * Researcher-facing extraction API (services/backend/extraction-service), proxied
 * under `${API_PREFIX}/extraction`. Includes its Swagger UI at `/extraction/docs`.
 *
 * Access: a logged-in, approved researcher or admin (session cookie), or a
 * personal API token from the web app's API Access page as a Bearer token.
 * The caller is forwarded to the extraction service as a short-lived signed JWT
 * (`X-Extraction-Principal`), which checks the roles again before exporting.
 */
const router = express.Router();

const FORWARDED_RESPONSE_HEADERS = ['content-type', 'content-disposition', 'cache-control'];

export const PRINCIPAL_HEADER = 'x-extraction-principal';
const PRINCIPAL_AUDIENCE = 'extraction-service';
const PRINCIPAL_TTL_SECONDS = 60;

/** Who is calling the extraction API. Read by the extraction service (src/app/auth.py). */
export interface ExtractionPrincipal {
  subject: string;
  roles: string[];
  auth: 'session' | 'api_token';
  /** `unverified`: API token whose owner is not in the in-memory user store, so no roles are known. */
  roleSource: 'verified' | 'unverified';
  tokenId?: string;
}

const rolesOf = (user: { isAdmin?: boolean; roles?: readonly string[] }): string[] => [
  ...(user.isAdmin ? ['admin'] : []),
  ...(user.roles ?? []),
];

export const signPrincipal = (principal: ExtractionPrincipal, secret: string): string =>
  jwt.sign(
    {
      roles: principal.roles,
      auth: principal.auth,
      role_source: principal.roleSource,
      ...(principal.tokenId ? { token_id: principal.tokenId } : {}),
    },
    secret,
    {
      algorithm: 'HS256',
      audience: PRINCIPAL_AUDIENCE,
      subject: principal.subject,
      expiresIn: PRINCIPAL_TTL_SECONDS,
    },
  );

const bearerToken = (req: Request): string | undefined => {
  const header = req.headers.authorization;
  if (!header?.startsWith('Bearer ')) return undefined;
  return header.slice('Bearer '.length).trim() || undefined;
};

export const requireExtractionAccess = async (
  req: Request,
  res: Response,
  next: NextFunction,
): Promise<void> => {
  const token = bearerToken(req);
  if (token !== undefined) {
    try {
      const check = await checkApiToken(token);
      if (!check.ok) {
        res.status(check.status).json({ error: check.error });
        return;
      }
      res.locals.apiTokenOwner = check.record.owner_email;
      res.locals.extractionPrincipal = {
        subject: check.record.owner_email,
        roles: check.owner ? rolesOf(check.owner) : [],
        auth: 'api_token',
        roleSource: check.owner ? 'verified' : 'unverified',
        tokenId: check.record.id,
      } satisfies ExtractionPrincipal;
      next();
    } catch (error) {
      logger.error('API token check failed', error as Error);
      res.status(503).json({ error: 'Token check unavailable, try again later' });
    }
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
  res.locals.extractionPrincipal = {
    subject: user.email,
    roles: rolesOf(user),
    auth: 'session',
    roleSource: 'verified',
  } satisfies ExtractionPrincipal;
  next();
};

router.get('/*', requireExtractionAccess, async (req: Request, res: Response) => {
  if (!config.extractionApiUrl || !config.extractionInternalJwtSecret) {
    res.status(503).json({ error: 'Extraction API is not configured' });
    return;
  }

  // req.url is relative to the mount point, e.g. /v1/measurements?patient_id=...
  const target = `${config.extractionApiUrl}${req.url}`;
  const abort = new AbortController();
  res.on('close', () => abort.abort());

  try {
    const upstream = await fetch(target, {
      headers: {
        accept: req.headers.accept ?? '*/*',
        [PRINCIPAL_HEADER]: signPrincipal(
          res.locals.extractionPrincipal as ExtractionPrincipal,
          config.extractionInternalJwtSecret,
        ),
      },
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
