import express from 'express';
import type { Request, Response } from 'express';
import { logger } from '../../logger.js';
import { auth } from '../../middleware.js';
import { createApiToken, listApiTokens, revokeApiToken } from '../../services/apiTokens.js';

/**
 * Personal tokens for the export API (/extraction). Mounted after auth.required,
 * so req.user is an approved user here.
 */
const router = express.Router();

const NAME_MAX_LENGTH = 100;
const MAX_ACTIVE_TOKENS_PER_USER = 10;

const fail = (res: Response, status: number, message: string, code?: string) =>
  res.status(status).json({ message, code });

router.get('/researcher/api-tokens', auth.researcherOrAdmin, async (req: Request, res: Response) => {
  try {
    return res.json(await listApiTokens({ ownerEmail: req.user!.email }));
  } catch (error) {
    logger.error('Error listing API tokens', error as Error);
    return fail(res, 500, 'Could not load your API tokens');
  }
});

router.post('/researcher/api-tokens', auth.researcherOrAdmin, async (req: Request, res: Response) => {
  const rawName = (req.body ?? {}).name;
  const name = typeof rawName === 'string' ? rawName.trim() : '';
  if (!name || name.length > NAME_MAX_LENGTH) {
    return fail(res, 400, `name is required (at most ${NAME_MAX_LENGTH} characters)`, 'INVALID_NAME');
  }

  try {
    const active = await listApiTokens({ ownerEmail: req.user!.email });
    if (active.length >= MAX_ACTIVE_TOKENS_PER_USER) {
      return fail(
        res,
        409,
        `You already have ${MAX_ACTIVE_TOKENS_PER_USER} active tokens. Revoke one first.`,
        'TOO_MANY_TOKENS',
      );
    }
    const { token, record } = await createApiToken(req.user!.email, name);
    logger.info('API token created', { tokenId: record.id, owner: record.owner_email });
    // The only time the plain token leaves the BFF.
    return res.status(201).json({ ...record, token });
  } catch (error) {
    logger.error('Error creating API token', error as Error);
    return fail(res, 500, 'Could not create the API token');
  }
});

router.post(
  '/researcher/api-tokens/:tokenId/revoke',
  auth.researcherOrAdmin,
  async (req: Request, res: Response) => {
    try {
      const own = await listApiTokens({ ownerEmail: req.user!.email, includeRevoked: true });
      if (!own.some((token) => token.id === req.params.tokenId)) {
        return fail(res, 404, 'Token not found', 'NOT_FOUND');
      }
      const record = await revokeApiToken(req.params.tokenId, req.user!.email);
      logger.info('API token revoked by owner', { tokenId: record.id });
      return res.json(record);
    } catch (error) {
      logger.error('Error revoking API token', error as Error);
      return fail(res, 500, 'Could not revoke the API token');
    }
  },
);

router.get('/admin/api-tokens', ...auth.adminOnly, async (req: Request, res: Response) => {
  try {
    return res.json(await listApiTokens({ includeRevoked: req.query.includeRevoked === 'true' }));
  } catch (error) {
    logger.error('Error listing API tokens', error as Error);
    return fail(res, 500, 'Could not load API tokens');
  }
});

router.post('/admin/api-tokens/:tokenId/revoke', ...auth.adminOnly, async (req: Request, res: Response) => {
  try {
    const all = await listApiTokens({ includeRevoked: true });
    if (!all.some((token) => token.id === req.params.tokenId)) {
      return fail(res, 404, 'Token not found', 'NOT_FOUND');
    }
    const record = await revokeApiToken(req.params.tokenId, req.user!.email);
    logger.info('API token revoked by admin', { tokenId: record.id, owner: record.owner_email });
    return res.json(record);
  } catch (error) {
    logger.error('Error revoking API token', error as Error);
    return fail(res, 500, 'Could not revoke the API token');
  }
});

export default router;
