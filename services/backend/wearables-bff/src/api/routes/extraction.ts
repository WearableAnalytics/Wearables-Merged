import express from 'express';
import jwt from 'jsonwebtoken';
import type { NextFunction, Request, Response } from 'express';
import { Readable } from 'stream';
import type { ReadableStream as WebReadableStream } from 'stream/web';
import config from '../../config.js';
import { logger } from '../../logger.js';
import { sendControlError } from '../../clients/controlApi.js';
import { getUserFromRequest } from '../../middleware.js';
import { checkApiToken } from '../../services/apiTokens.js';

/**
 * Extraction API (services/backend/extraction-service), proxied under
 * `${API_PREFIX}/extraction`. Includes its Swagger UI at `/extraction/docs`.
 *
 * Access: a logged-in, approved admin, practitioner or researcher (session
 * cookie), or a researcher's/admin's personal API token from the web app's API
 * Access page as a Bearer token. The caller is forwarded to the extraction
 * service as a short-lived signed JWT (`X-Extraction-Principal`), which checks
 * the roles again and always pseudonymizes the data for researchers.
 */
const router = express.Router();

// Cache-Control is set by the BFF itself (no-store on every response, see server.ts).
const FORWARDED_RESPONSE_HEADERS = [
  'content-type',
  'content-disposition',
  'x-export-considered',
  'x-export-exported',
  'x-export-omitted',
  'x-export-omitted-unsupported',
  'x-export-omitted-invalid-value',
];

export const PRINCIPAL_HEADER = 'x-extraction-principal';
const PRINCIPAL_AUDIENCE = 'extraction-service';
const PRINCIPAL_TTL_SECONDS = 60;

/** Who is calling the extraction API. Read by the extraction service (src/app/auth.py). */
export interface ExtractionPrincipal {
  subject: string;
  roles: string[];
  auth: 'session' | 'api_token';
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
        roles: rolesOf(check.owner),
        auth: 'api_token',
        tokenId: check.record.id,
      } satisfies ExtractionPrincipal;
      next();
    } catch (error) {
      logger.error('API token check failed', error as Error);
      res
        .status(503)
        .json({ error: 'Token check unavailable, try again later' });
    }
    return;
  }

  let user;
  try {
    user = await getUserFromRequest(req);
  } catch (error) {
    if (!sendControlError(res, error))
      res.status(503).json({ error: 'Account authority unavailable' });
    return;
  }
  if (!user) {
    res.status(401).json({ error: 'Authentication required' });
    return;
  }
  if (user.status === 'pending' || user.status === 'denied') {
    res
      .status(403)
      .json({ error: 'Account not approved', code: 'ACCOUNT_NOT_APPROVED' });
    return;
  }
  // Practitioners only through their login session: API tokens stay researcher/admin (checkApiToken).
  if (!user.isAdmin && !user.roles?.some((role) => role === 'researcher' || role === 'practitioner')) {
    res.status(403).json({
      error: 'Admin, practitioner or researcher access required',
      code: 'EXTRACTION_ACCESS_REQUIRED',
    });
    return;
  }
  req.user = user;
  res.locals.extractionPrincipal = {
    subject: user.email,
    roles: rolesOf(user),
    auth: 'session',
  } satisfies ExtractionPrincipal;
  next();
};

router.get(
  '/*',
  requireExtractionAccess,
  async (req: Request, res: Response) => {
    if (!config.extractionApiUrl) {
      res.status(503).json({ error: 'Extraction API is not configured' });
      return;
    }
    if (!config.extractionInternalJwtSecret) {
      // Warned about at startup (config.ts); set it with scripts/bootstrap-runtime-secrets.sh.
      res.status(503).json({ error: 'Extraction API authentication is not configured' });
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
  },
);

export default router;
