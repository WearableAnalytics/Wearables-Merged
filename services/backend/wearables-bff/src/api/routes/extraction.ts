import express from 'express';
import type { NextFunction, Request, Response } from 'express';
import { logger } from '../../logger.js';
import { getUserFromRequest } from '../../middleware.js';
import { checkApiToken } from '../../services/apiTokens.js';

/**
 * Researcher-facing extraction API (services/backend/extraction-service), proxied
 * under `${API_PREFIX}/extraction`. Includes its Swagger UI at `/extraction/docs`.
 *
 * Access: a logged-in, approved researcher or admin (session cookie), or a
 * personal API token from the web app's API Access page as a Bearer token.
 */
const router = express.Router();


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
      next();
    } catch (error) {
      logger.error('API token check failed', error as Error);
      res.status(503).json({ error: 'Token check unavailable, try again later' });
    }
    return;
  }

  const user = await getUserFromRequest(req);
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

// The legacy proxy accepts arbitrary patient/query parameters. A login role is
// not enough to enforce a case assignment. Preserve the implementation in Git,
// but do not send data until a case-scoped export API is reviewed separately.
router.all('/*', (_req, res) => {
  res.status(410).setHeader('Cache-Control', 'no-store');
  res.json({ code: 'CASE_SCOPED_EXPORT_REQUIRED', error: 'Legacy exports are paused until case-scoped access is available.' });
});

export default router;
